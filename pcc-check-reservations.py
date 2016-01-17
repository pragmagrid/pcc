#!/usr/bin/env python

"""pcc-check-reservations.py

Queries Booked and checks for reservations that need to be started or stopped.
Configuration for script is held in cloud-scheduler.cfg file

Example:
      $ pcc-check-reservations.py

cloud-scheduler.cfg attributes:
  Authentication:
    username: username to authenticate to Booked 
    password: password to authenticate to Booked 
  Server
    hostname: Booked hostname
  Logging
    file: name of log file
    level: verbosity of logging (INFO, DEBUG)
  Stopping
    reservationSecsLeft: stop PCC when specified secs left in reservation 
"""

from ConfigParser import ConfigParser
from datetime import datetime
from httplib import HTTPConnection
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
from string import Template
import socket
import subprocess
import sys
import time

ISO_FORMAT="%Y-%m-%dT%H:%M:%S" 
ISO_LENGTH=19

NODE_TEMPLATE = """
universe                     = vm
executable                   = rocks_vc_$id
requirements                 = Machine =="$host"
log                          = vc$id.log.txt
vm_type                      = rocks
vm_memory                    = $memory
rocks_job_dir                  = $jobdir
JobLeaseDuration             = 7200
RequestMemory = $memory
pragma_boot_version          = $version
rocks_should_transfer_files = Yes
RunAsOwner=True
queue
"""

VMCONF_TEMPLATE = """--executable      = pragma_boot
--key             = $sshKeyPath
--num_cpus       = $cpus       
--vcname          = $vcname
--logfile         = $jobdir/pragma_boot.log
"""
#--enable-ipop-server=http://nbcr-224.ucsd.edu/ipop/exchange.php?jobId=$jobid

EMAIL_STARTING_TEMPLATE = """----- PRAGMA Cloud Scheduler Update @ $date -----

Your resource reservation is being started.  You will receive an email when
the resources are ready for you to login.

"""

EMAIL_STARTED_TEMPLATE = """----- PRAGMA Cloud Scheduler Update @ $date -----

Your resource reservation has been activated: $resourceinfo

To access resources, login to the frontend.  E.g.,

> ssh root@$fqdn

"""

def query( connection, path, method, params, headers ):
  """Send a REST API request

    Args:
      connection(HTTPConnection): An already open HTTPConnection
      path(string): REST API path function
      method(string): POST or GET
      params(string): Arguments to REST function
      headers(string): HTTP header info containing auth data

    Returns:
      JSON object: response from server
  """
  connection.request( method, path, json.dumps(params), headers )
  response = connection.getresponse()
  if response.status != 200:
    sys.stderr.write( "Problem querying " + path + ": " + response.reason )
    sys.stderr.write( response.read() )
    sys.exit(1)
  responsestring = response.read()
  return json.loads( responsestring )


def queryBooked( config, function, method, params, headers ):
  """Send a Booked REST API request

    Args:
      config(ConfigParser): Config file input data
      function(string): Name of Booked REST API function
      method(string): POST or GET
      params(string): Arguments to REST function
      headers(string): HTTP header info containing auth data

    Returns:
      dict: contains Booked auth info
      JSON object: response from server
  """
  connection = HTTPConnection( config.get("Server", "hostname") )
  connection.connect()

  if headers == None:
    creds = { 
        "username": config.get("Authentication", "username"), 
        "password": config.get("Authentication", "password") 
    }
    authUrl = config.get("Server", "baseUrl") + "Authentication/Authenticate"
    session = query( connection, authUrl, "POST", creds, {} )
    headers = { 
      "X-Booked-SessionToken": session['sessionToken'], 
      "X-Booked-UserId": session['userId']
    }

  url = config.get("Server", "baseUrl") + function 
  data = query( connection, url, method, params, headers )
  connection.close()
  return (headers, data)

def updateStatus( data, status, config, headers ):
  """Send reservation update request

    Args:
      data(JSON): Reservation JSON data from a GET request
      status(string): new status for reservation
      config(ConfigParser): Config file input data
      headers(string): HTTP header info containing auth data

    Returns:
      bool: True if successful, False otherwise.
  """
  updateData = json.loads(  json.dumps(data) )
  reformattedAttributes = [];
  # need to reformat attributes to just the ids and values
  for attr in updateData['customAttributes']:
    if "id" in attr.keys() and "value" in attr.keys():
      reformattedAttributes.append( { 
        'attributeId' : attr['id'],
        'attributeValue' : attr['value'] } )
    else:
      print "Bad attr " + str(attr)
  updateData['customAttributes'] = reformattedAttributes
  # need to reformat resources to just the ids
  reformattedResources = [];
  for resource in updateData['resources']:
    reformattedResources.append(resource['id'])
  updateData['resources'] = reformattedResources
  updateData['statusId'] = config.get( "Status", status )
  (headers, responsedata) = queryBooked( config, "Reservations/"+bookedReservation["referenceNumber"], "POST", updateData, headers )
  logging.debug( "  Server response was: " + responsedata['message'] )
  return responsedata['message'] == 'The reservation was updated'

def convertAttributesToDict( attrs ):
  """Convert Booked-style attrs to name/value attrs

    Args:
      attrs(): Reservation JSON data from a GET request

    Returns:
      dict: where key is attr name and value is attr value
  """
  dictAttrs = {}
  for attr in attrs:
    dictAttrs[attr['label']] = attr['value']
  return dictAttrs

def writeDag( dagDir, data, config, headers ):
  """Write a Condor DAG to localdisk 

    The following files will be generated:
    dag-{referenceNumber}
      dag-{referenceNumber}/dag.sub - Top level dag
      dag-{referenceNumber}/public_key - User's SSH public key
    dag-{referenceNumber}/vc{resourceId} - dir for each resource
      dag-{referenceNumber}/vc{resourceId}/vc{resourceId}.sub - condor.sub file
      dag-{referenceNumber}/vc{resourceId}/vc{resourceId}.vmconf - pragma_boot args

    Args:
      dagDir(string): Path to directory to store Condor DAGs
      data(JSON): Reservation JSON data from a GET request
      config(ConfigParser): Config file input data
      headers(string): HTTP header info containing auth data

    Returns:
      string: path to the dir where dag was written
  """
  # get reservation info
  reservAttrs = convertAttributesToDict( data['customAttributes'] )

  # get user info
  (headers, userdata) = queryBooked( config, "/Users/"+data['owner']['userId'], "GET", None, headers );
  userAttrs = convertAttributesToDict( userdata['customAttributes'] )

  # make dag dir and write user's key to disk
  dagDir = os.path.join( dagDir, "dag-" + data["referenceNumber"] )
  if not os.path.exists(dagDir):
    logging.debug( "  Creating dag directory " + dagDir )
    os.makedirs(dagDir)
    dagDir = os.path.abspath(dagDir)
  rf = open( '/root/.ssh/id_rsa.pub', 'r' )
  root_key = rf.read()
  rf.close()
  sshKeyPath = os.path.join(dagDir, "public_key")
  f = open( sshKeyPath, 'w' )
  logging.debug( "  Writing file " + f.name );
  f.write(userAttrs['SSH public key'] + "\n");
  f.write( "%s\n" % root_key );
  f.close()

  # write dag file
  dag_f = open(os.path.join(dagDir,"dag.sub"), 'w')
  logging.debug( "  Writing file " + dag_f.name );

  # create dag node files for each resource in reervation
  for resource in data['resources']:
    dagNodeDir = os.path.join( dagDir, "vc" + resource["id"] )
    if not os.path.exists(dagNodeDir):
      logging.debug( "  Creating dag node directory " + dagNodeDir )
      os.mkdir(dagNodeDir)
    # get resource info
    (headers, resourcedata) = queryBooked( config, "/Resources/"+resource["id"], "GET", None, headers );
    resourceAttrs = convertAttributesToDict( resourcedata['customAttributes'] )
    f = open(os.path.join(dagNodeDir,"vc"+resource["id"]+".sub"), 'w')
    logging.debug( "  Writing file " + f.name );
    dag_f.write( " JOB VC%s  %s\n" % (resource["id"], f.name) )
    s = Template(NODE_TEMPLATE)
    f.write(s.substitute(id=resource["id"], host=resourceAttrs['Site hostname'], version=resourceAttrs['Pragma_boot version'], memory=reservAttrs['Memory (GB)'], jobdir=dagDir))
    f.close()
    f = open(os.path.join(dagNodeDir,"vc"+resource["id"]+".vmconf"), 'w')
    logging.debug( "  Writing file " + f.name );
    s = Template(VMCONF_TEMPLATE)
    f.write( s.substitute(cpus=reservAttrs['CPUs'], vcname=reservAttrs['VC Name'], sshKeyPath=sshKeyPath, jobdir=dagDir, jobid=os.getpid()) )
    f.close()

  # close out dag file
  dag_f.close()
  return dagDir

def getRegexFromFile( file, regex ):
  """Grab some strings from a file based on a regex

    Args:
      file(string): Path to file containing string
      regex(string): Regex to parse from file

    Returns:
      list: Args returned from regex
  """
  f = open( file, "r" )
  matcher = re.compile( regex, re.MULTILINE );
  matched = matcher.search( f.read() )
  f.close()
  if not matched:
    return []
  elif len(matched.groups()) == 1:
    return matched.group(1)
  else:
    return matched.groups()

def writeStringToFile( file, aString ):
  """Write a string to file

    Args:
      file(string): Path to file containing string
      aString(string): string to write to file

    Returns:
      bool: True if success otherwise false
  """
  f = open( file, 'w' )
  f.write( aString )
  return f.close()

def isDagRunning( dagDir ):
  """Check to see if dag is running

    Args:
      dagDir(string): Path to directory to store Condor DAGs

    Returns:
      bool: True if dag is running, False otherwise.
  """
  (active,inactive, resourceinfo, frontendFqdn) = ([],[], "", "")
  subf = open( os.path.join(dagDir, 'dag.sub'), 'r' )
  for line in subf:
    matched = re.match( ".*\s(\S+)$", line )
    if matched:
      vcdir = os.path.dirname( matched.group(1) )
      hostname = getRegexFromFile( os.path.join(vcdir, "hostname"), "(.*)" )
      cluster_info_filename = os.path.join(vcdir, "cluster_info");
      (cluster_fqdn, nodes) = ("", [])
      if not os.path.exists( cluster_info_filename ):
        scp = 'scp %s:%s %s >& /dev/null' % (hostname, os.path.join(dagDir,"pragma_boot.log"), vcdir)
        logging.debug( "  %s" % scp )
        subprocess.call( scp, shell=True)
        cluster_fqdn = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'fqdn=(\S+)*' )
        if not cluster_fqdn:
          cluster_fqdn = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'Found available public IP [\d\.]+ -> (\S+)' )
          if not cluster_fqdn:
            logging.info( "   No FQDN info available yet" )
            return False
        nodes.append( cluster_fqdn.split(".")[0] )
        try:
          numcpus = int(getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'numcpus=(.+)' ) )
        except:
          numcpus = int(getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'Requesting (\d+) CPUs' ) )
        cnodes = ""
        if numcpus > 0:
          try:
            cnodes = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), "cnodes='?([^']+)" )
            cnodes_array = cnodes.split( "\n" )
          except:
            cnodes = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), "Allocated cluster \S+ with compute nodes: (.+)" )
            cnodes_array = cnodes.split( ", " )
          if not cnodes:
            logging.info( "   No compute nodes info available yet" )
            continue
          nodes.extend( cnodes_array )
          cnodes = " ".join(cnodes_array)
        writeStringToFile( os.path.join(vcdir, "cluster_info"), "fqdn=%s\ncnodes=%s" % (cluster_fqdn, cnodes) ) 
      else:
        logging.debug( "  Reading %s" % cluster_info_filename )
        cluster_fqdn = getRegexFromFile( cluster_info_filename, "fqdn=(.*)" )
        nodes.append( cluster_fqdn.split(".")[0] )
        cnodes = getRegexFromFile( cluster_info_filename, "cnodes=(.*)" )
        if len(cnodes) > 0:
          nodes.extend( re.split("\s+", cnodes) )
      frontendFqdn = cluster_fqdn
      resourceinfo += "\n\nFrontend: %s\nNumber of compute nodes: %d" % (cluster_fqdn, len(nodes)-1);
      rocks_status_filename =  os.path.join( vcdir, "rocks_list_host_vm" )
      stdout_f = open( rocks_status_filename, "w" )
      ssh = 'ssh %s rocks list host vm status=true' % hostname
      logging.debug( "  Writing '%s' to %s" % (ssh, rocks_status_filename) )
      subprocess.call(ssh, stdout=stdout_f, shell=True)
      stdout_f.close()
      for node in nodes:
        status = getRegexFromFile( rocks_status_filename, "(%s:.*active)" % node )
        logging.debug( "  Checking status of node %s is %s" % (node, status) )
        if len(status) > 0:
          active.append(node)
        else:
          inactive.append(node)
  subf.close()
  logging.info( "   Active nodes: %s" % str(active) )
  logging.info( "   Inactive nodes: %s" % str(inactive) )
  if len(inactive) == 0:
    ping = 'ping -c 1 %s >& /dev/null' % cluster_fqdn
    ping_status = subprocess.call(ping, shell=True)
    logging.debug( "  Ping to '%s': %i" % (cluster_fqdn, ping_status) )
    if ping_status != 0:
      inactive.append(cluster_fqdn)
  if len(inactive) == 0:
    s = Template(EMAIL_STARTED_TEMPLATE)
    return s.substitute(date=str(datetime.now()), resourceinfo=resourceinfo, fqdn=frontendFqdn)
  return None;

def startDagPB( dagDir ):
  """Start the dag using pragma_boot directly via SSH

    Args:
      dagDir(string): Path to directory to store Condor DAGs
      headers(string): HTTP header info containing auth data

    Returns:
      bool: True if writes successful, False otherwise.
  """
  local_hostname = socket.gethostname()
  subf = open( os.path.join(dagDir, 'dag.sub'), 'r' )
  for line in subf:
    matched = re.match( ".*\s(\S+)$", line )
    if matched:
      vcfile = matched.group(1)
      vcf = open( vcfile, 'r' );
      vcf_content = vcf.read()
      vcf.close()
      matched = re.match( '.*Machine =="([^"]+)".*', vcf_content, re.DOTALL )
      hostname = matched.group(1)

      #matched = re.search( '.*pragma_boot_version\s*=\s*(\d+)".*', vcf_content, re.DOTALL )
      matched = re.search( 'pragma_boot_version\s*=\s*(\d+)', vcf_content, re.DOTALL )
      pragma_boot_version = matched.group(1)

      host_f = open( os.path.join(os.path.dirname(vcfile), "hostname"), 'w' )
      host_f.write( hostname )
      host_f.close()
      if hostname != local_hostname: 
        logging.debug( "  Copying dir %s over to %s:%s " % (dagDir,hostname, dagDir) )
        subprocess.call('ssh %s mkdir -p /var/run/pcc' % hostname, shell=True)
        subprocess.call('scp -r %s %s:%s' % (dagDir, hostname, dagDir), shell=True)
      vmconf_file = vcfile.replace( '.sub', '.vmconf' )
      vmf = open( vmconf_file, 'r' );
      args = ""
      cmdline = ""
      if pragma_boot_version == "1":
        for line in vmf:
          matched = re.match( "(--\S+)\s+=\s+(.*)", line )
          if matched and matched.group(1) != '--executable' and matched.group(1) != '--logfile':
            args += " %s=%s" % (matched.group(1), matched.group(2))
        cmdline = "ssh -f %s 'cd %s; /opt/pragma_boot/bin/pragma_boot %s' >& %s/ssh.out" % (hostname, dagDir, args, dagDir)
      elif pragma_boot_version == "2":
        args = {}
        for line in vmf:
          matched = re.match( "--(\S+)\s+=\s+(\S+)", line )
          args[matched.group(1)] = matched.group(2)
        cmdline = "ssh -f %s 'cd %s; /opt/python/bin/python /opt/pragma_boot/bin/pragma boot %s %s key=%s loglevel=DEBUG logfile=%s' >& %s/ssh.out" % (hostname, dagDir, args["vcname"], args["num_cpus"], args["key"], args["logfile"], dagDir)
      else:
        logging.error("Error, unknown pragma_boot version %s" % pragma_boot_version)
        sys.exit(1)
      logging.debug( "  Running pragma_boot: %s: " % cmdline )
      subprocess.call(cmdline, shell=True)
  subf.close()
  logging.debug( "  Sleeping 10 seconds" )
  time.sleep(10)
  return True

# read input arguments from property file
config = ConfigParser()
config.read("cloud-scheduler.cfg");
reservationSecsLeft = int( config.get( "Stopping", "reservationSecsLeft" ) );

# configure logging 
logger = logging.getLogger()
logger.setLevel( config.get("Logging", "level") )
handler = TimedRotatingFileHandler(
  config.get("Logging", "file"), when="W0", interval=1, backupCount=5
)
handler.setFormatter(
  logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(handler)

# Examine all reservations and determine which require actions
logging.debug( "Reading current and future reservations" )
(headers, data) = queryBooked( config, "Reservations/", "GET", None, None );

# if reservation contains more than one resource, one entry is returned for
# each; we just need one
bookedReservations = {}
for bookedReservation in data["reservations"]:
  bookedReservations[bookedReservation['referenceNumber']] = bookedReservation

# Iterate thru unique reservations
for bookedReservation in bookedReservations.values():
  (headers, data) = queryBooked( config, "Reservations/"+bookedReservation["referenceNumber"], "GET", None, headers );
  # Gather reservation data info
  logging.debug( "Reservation: ref=%s, status=%s, resourceId=%s" % (bookedReservation["referenceNumber"], data['statusId'], data['resourceId']) )
  startTime = datetime.strptime( data['startDateTime'][:ISO_LENGTH], ISO_FORMAT )
  endTime = datetime.strptime( data['endDateTime'][:ISO_LENGTH], ISO_FORMAT )
  now = datetime.now()
  logging.debug( "  Start: " + data['startDateTime'] + ", End: " + data['endDateTime'] ) 
  startDiff = startTime - now
  endDiff = endTime - now

  # Reservation needs to be started
  if ( config.get("Status", "created") == data['statusId'] ):
    logging.debug( "  Reservation should be started in: " + str(startDiff) )
    if startDiff.total_seconds() <= 0: # should be less than
      logging.info( "   Starting reservation at " + str(datetime.now()) )
      dagDir = writeDag( config.get("Server", "dagDir"), data, config, headers )
      startDagPB( dagDir )
      s = Template(EMAIL_STARTING_TEMPLATE)
      data['description'] += "\n\n%s" % s.substitute(date=str(datetime.now()))
      updateStatus( data, "starting", config, headers )
  # else Reservation is starting
  elif config.get("Status", "starting") == data['statusId']: 
    logging.info( "   Checking status of reservation " )
    dagDir = os.path.join( config.get("Server", "dagDir"), "dag-" + data["referenceNumber"] )
    info = isDagRunning( dagDir )
    if info:
      logging.info( "   Reservation is running" )
      data['description'] += "\n\n%s" % info
      updateStatus( data, "running", config, headers ) 
  # else Reservation is running
  elif ( config.get("Status", "running") == data['statusId'] and endDiff.total_seconds() > reservationSecsLeft ):
    # <insert pcc check to make sure is true>
    shutdownTime = endDiff.total_seconds() - reservationSecsLeft
    logging.debug( "  Reservation scheduled to be shut down in %s or %d secs" % (str(endDiff), shutdownTime) )
  # else Reservation is running and needs to be shut down
  elif ( config.get("Status", "running") == data['statusId'] and endDiff.total_seconds() <= reservationSecsLeft ):
    logging.debug( "  Reservation has expired; shutting down cluster" )
    updateStatus(data, "stopping",config, headers )
  # else Reservation is stopping but time hasn't expired yet
  elif config.get("Status", "stopping") == data['statusId']: 
    # <insert check if pcc is done>
    logging.info( "   PCC has finished shutting down " + str(datetime.now()) )
    updateStatus( data, "created", config, headers ) 
  # else reservation is active/future and unknown state
  else:
    logging.debug( "  Reservation in unknown state to PCC" )

