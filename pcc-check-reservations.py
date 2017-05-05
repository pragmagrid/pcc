#!/opt/python/bin/python

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
import glob
from httplib import HTTPSConnection
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
from string import Template
import socket
import ssl
import subprocess
import sys
import time
import urllib

ISO_FORMAT="%Y-%m-%d %H:%M:%S" 
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
pragma_boot_path             = $pragma_boot_path
python_path                  = $python_path
username                     = $username
var_run                      = $var_run
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

EMAIL_STOPPING_TEMPLATE = """----- PRAGMA Cloud Scheduler Update @ $date -----

Your resource reservation is being shutdown.

"""

EMAIL_STOPPED_TEMPLATE = """----- PRAGMA Cloud Scheduler Update @ $date -----

Your resource reservation has been shutdown

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
  if headers is None:
    headers = {}
  connection.request( method, path, urllib.urlencode(params), headers )
  response = connection.getresponse()
  if response.status != 200:
    sys.stderr.write( "Problem querying " + path + ": " + response.reason )
    sys.stderr.write( response.read() )
    sys.exit(1)
  responsestring = response.read()
  return json.loads( responsestring )


def queryGUI( config, function, method, params, headers ):
  """Send a GUI API request

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
  connection = HTTPSConnection( config.get("Server", "hostname"), context=ssl._create_unverified_context() )
  connection.connect()

  if headers == None:
    creds = { 
        "username": config.get("Authentication", "username"), 
        "password": config.get("Authentication", "password") 
    }
    authUrl = config.get("Server", "baseUrl") + "signIn.py"
    session = query( connection, authUrl, "POST", creds, {} )
    if params is None:
      params = {}
    params["session_id"] = session["session_id"]

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
  (headers, responsedata) = queryGUI( config, "Reservations/"+bookedReservation["referenceNumber"], "POST", updateData, headers )
  logging.debug( "  Server response was: " + responsedata['message'] )
  return responsedata['message'] == 'The reservation was updated'

def runShellCommand( cmd, stdout_filename):
  """Run bash shell command

    Args:
      stdout_filename: put stdout in specified filename

    Returns:
      exit code of cmd
  """

  stdout_f = open(stdout_filename, "w" )
  result = subprocess.call(cmd, stdout=stdout_f, shell=True)
  stdout_f.close()

  f = open(stdout_filename, "r")
  stdout_text = f.read()
  f.close()
  return (result, stdout_text)

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
  (headers, userdata) = queryGUI( config, "/Users/"+data['owner']['userId'], "GET", None, headers );
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
    (headers, resourcedata) = queryGUI( config, "/Resources/"+resource["id"], "GET", None, headers );
    resourceAttrs = convertAttributesToDict( resourcedata['customAttributes'] )
    f = open(os.path.join(dagNodeDir,"vc"+resource["id"]+".sub"), 'w')
    logging.debug( "  Writing file " + f.name );
    dag_f.write( " JOB VC%s  %s\n" % (resource["id"], f.name) )
    s = Template(NODE_TEMPLATE)
    # optional params
    python_path = "" if resourceAttrs['Python path'] is None else resourceAttrs['Python path']
    f.write(s.substitute(id=resource["id"], host=resourceAttrs['Site hostname'], pragma_boot_path=resourceAttrs['Pragma_boot path'], python_path=python_path, version=resourceAttrs['Pragma_boot version'], username=resourceAttrs['Username'], var_run=resourceAttrs['Temporary directory'], memory=reservAttrs['Memory (GB)'], jobdir=dagDir))
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
  matcher = re.compile( regex, re.MULTILINE )
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

def isDagRunning( dagDir, refNumber ):
  """Check to see if dag is running

    Args:
      dagDir(string): Path to directory to store Condor DAGs

    Returns:
      bool: True if dag is running, False otherwise.
  """
  (active, inactive, resourceinfo, frontendFqdn) = ([], [], "", "")
  subf = open( os.path.join(dagDir, 'dag.sub'), 'r' )
  for line in subf:
    matched = re.match( ".*\s(\S+)$", line )
    if matched:
      vcdir = os.path.dirname( matched.group(1) )
      hostname = getRegexFromFile( os.path.join(vcdir, "hostname"), "(.*)" )
      [conf] = glob.glob(os.path.join(vcdir, "*.sub"))
      username = getRegexFromFile( conf, "username\s*=\s*(.*)" )
      var_run = getRegexFromFile( conf, "var_run\s*=\s*(.*)" )
      pragma_boot_path = getRegexFromFile( conf, "pragma_boot_path\s*=\s*(.*)" )
      python_path = getRegexFromFile( conf, "python_path\s*=\s*?(\S*?)$" )
      pragma_boot_version = getRegexFromFile( conf, "pragma_boot_version\s*=\s*(.*)" )
      remoteDagDir = os.path.join( var_run, "dag-%s" % refNumber )
      cluster_info_filename = os.path.join(vcdir, "cluster_info");
      (cluster_fqdn, nodes) = ("", [])

      if pragma_boot_version == "2":
        scp = 'scp %s@%s:%s %s >& /dev/null' % (username, hostname, os.path.join(remoteDagDir,"pragma_boot.log"), vcdir)
        logging.debug( "  %s" % scp )
        subprocess.call( scp, shell=True)
        frontend = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'Allocated cluster (\S+)' )
        if not frontend:
          frontend = getRegexFromFile( os.path.join(vcdir,"pragma_boot.log"), 'Successfully deployed frontend (\S+)' )
        ssh = 'ssh %s@%s %s %s/bin/pragma list cluster %s' % (username, hostname, python_path, pragma_boot_path, frontend)
        pragma_status_filename =  os.path.join( vcdir, "pragma_list_cluster" )
        stdout_f = open(pragma_status_filename, "w" )
        result = subprocess.call(ssh, stdout=stdout_f, shell=True)
        stdout_f.close()
        f = open(pragma_status_filename, "r")
        status = f.readlines()
        f.close()
	status.pop(0) # discard header
        isRunning = True
        runningMatcher = re.compile("Running|active")
        ipMatcher = re.compile("([\d\.]+)\s*$")
        publicIP = None
        for line in status:
          if not runningMatcher.search(line):
            isRunning = False
          else:
            matched = ipMatcher.search(line)
            if matched:
              publicIP = matched.group(1)
        accessible = False
        if publicIP:
          logging.info("   Found public IP %s" % publicIP)
          ssh = 'echo | nc -w 30 %s 22 2>&1 | grep SSH > /dev/null 2>&1' % (publicIP)
          result = subprocess.call(ssh, shell=True)
          if result == 0:
            logging.info("   SSH is active on %s" % publicIP)
            accessible = True
          else:
            logging.info("   SSH is not yet active on %s" % publicIP)
        if isRunning and accessible:
          active.append(frontend)
        else:
          inactive.append(frontend)
        logging.info("   %s" % status)
      else:
        logging.error("Error, unknown or unsupported pragma_boot version %s" % pragma_boot_version)
        sys.exit(1)
  logging.info( "   Active clusters: %s" % str(active) )
  logging.info( "   Inactive clusters: %s" % str(inactive) )
  subf.close()
  if len(inactive) == 0:
    s = Template(EMAIL_STARTED_TEMPLATE)
    return s.substitute(date=str(datetime.now()), resourceinfo=resourceinfo, fqdn=publicIP)
  return None

def startDagPB( dagDir, refNumber ):
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
      hostname = getRegexFromFile( vcfile, 'Machine =="([^"]+)"' )
      username = getRegexFromFile( vcfile, "username\s*=\s*(.*)" )
      pragma_boot_path = getRegexFromFile( vcfile, "pragma_boot_path\s*=\s*(\S+)" )
      python_path = getRegexFromFile( vcfile, "python_path\s*=\s*?(\S*?)$" )
      pragma_boot_version = getRegexFromFile( vcfile, "pragma_boot_version\s*=\s*(\S+)" )
      var_run = getRegexFromFile( vcfile, "var_run\s*=\s*(\S+)" )
      remoteDagDir = os.path.join( var_run, "dag-%s" % refNumber )

      host_f = open( os.path.join(os.path.dirname(vcfile), "hostname"), 'w' )
      host_f.write( hostname )
      host_f.close()
      if hostname != local_hostname: 
        logging.debug( "  Copying dir %s over to %s:%s " % (dagDir,hostname, remoteDagDir) )
        subprocess.call('ssh %s@%s mkdir -p %s' % (username, hostname, var_run), shell=True)
        subprocess.call('scp -r %s %s@%s:%s >& /dev/null' % (dagDir, username, hostname, remoteDagDir), shell=True)
      vmconf_file = vcfile.replace( '.sub', '.vmconf' )
      vmf = open( vmconf_file, 'r' );
      args = ""
      cmdline = ""
      if pragma_boot_version == "2":
        args = {}
        for line in vmf:
          matched = re.match( "--(\S+)\s+=\s+(\S+)", line )
          args[matched.group(1)] = matched.group(2)
        args["key"] = args["key"].replace(dagDir, remoteDagDir)
        args["logfile"] = args["logfile"].replace(dagDir, remoteDagDir)
        cmdline = "ssh -f %s@%s 'cd %s; %s %s/bin/pragma boot %s %s key=%s loglevel=DEBUG logfile=%s' >& %s/ssh.out" % (username, hostname, remoteDagDir, python_path, pragma_boot_path, args["vcname"], args["num_cpus"], args["key"], args["logfile"], dagDir)
      else:
        logging.error("Error, unknown or unsupported pragma_boot version %s" % pragma_boot_version)
        sys.exit(1)
      logging.debug( "  Running pragma_boot: %s" % cmdline )
      subprocess.call(cmdline, shell=True)
  subf.close()
  logging.debug( "  Sleeping 10 seconds" )
  time.sleep(10)
  return True

def stopDagPB( dagDir, refNumber ):
  """Stop the dag using pragma_boot directly via SSH

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
      vcdir = os.path.dirname( matched.group(1) )
      hostname = getRegexFromFile( vcfile, 'Machine =="([^"]+)"' )
      username = getRegexFromFile( vcfile, "username\s*=\s*(.*)" )
      pragma_boot_path = getRegexFromFile( vcfile, "pragma_boot_path\s*=\s*(\S+)" )
      python_path = getRegexFromFile( vcfile, "python_path\s*=\s*?(\S*?)$" )
      frontend = getRegexFromFile( os.path.join(dagDir,"pragma_boot.log"), 'Allocated cluster (\S+)' )
      ssh_pragma = "ssh %s@%s %s %s/bin/pragma" % (username, hostname, python, pragma_boot_path)
      shutdown_cmd = "%s shutdown %s" % (ssh_pragma, frontend)
      logger.debug("  Shutting down %s: %s" % (frontend, shutdown_cmd))
      (result, stdout_text) = runShellCommand(shutdown_cmd, os.path.join(vcdir, "pragma_shutdown"))
      if result != 0:
        logger.error("  Error shutting down virtual cluster %s" % frontend)
        return False
      logger.debug("  %s" % stdout_text)
      clean_cmd = "%s clean %s" % (ssh_pragma, frontend)
      logger.debug("  Cleaning %s: %s" % (frontend, clean_cmd))
      (result, stdout_text) = runShellCommand(clean_cmd, os.path.join(vcdir, "pragma_clean"))
      logger.debug("  %s" % stdout_text)
      if result != 0:
        logger.error("  Error cleaning virtual cluster %s" % frontend)
        return False
  return True

# main

# read input arguments from property file
config = ConfigParser()
config.read("cloud-scheduler.cfg");
reservationSecsLeft = int( config.get( "Stopping", "reservationSecsLeft" ) );

# configure logging 
logger = logging.getLogger()
#logger.setLevel( config.get("Logging", "level") )
#handler = TimedRotatingFileHandler(
#  config.get("Logging", "file"), when="W0", interval=1, backupCount=5
#)
#handler.setFormatter(
#  logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
#)
#logger.addHandler(handler)
logging.basicConfig(
		format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
		level=config.get("Logging", "level"))

# Examine all reservations and determine which require actions
logging.debug( "Reading current and future reservations" )
(headers, data) = queryGUI( config, "/getAllReservations.py", "POST", None, None );

# if reservation contains more than one resource, one entry is returned for
# each; we just need one
bookedReservations = {}
for bookedReservation in data["result"]:
  bookedReservations[bookedReservation['reservation_id']] = bookedReservation

print bookedReservations

# Iterate thru unique reservations
for bookedReservation in bookedReservations.values():
  # Gather reservation data info
  for site in bookedReservation["sites"]:
    logging.debug( "Reservation: ref=%s, status=%s, resourceId=%s" % (bookedReservation["reservation_id"], site['status'], site['site_name']) )
  startTime = datetime.strptime( bookedReservation['begin'][:ISO_LENGTH], ISO_FORMAT )
  endTime = datetime.strptime( bookedReservation['end'][:ISO_LENGTH], ISO_FORMAT )
  now = datetime.now()
  logging.debug( "  Start: " + bookedReservation['begin'] + ", End: " + bookedReservation['end'] ) 
  startDiff = startTime - now
  endDiff = endTime - now

  for site in bookedReservation["sites"]:
    # Reservation needs to be started
    if site['status'] == 'waiting':
      logging.debug( "  Reservation should be started in: " + str(startDiff) )
      if startDiff.total_seconds() <= 0: # should be less than
        logging.info( "   Starting reservation at " + str(datetime.now()) )
        dagDir = writeDag( config.get("Server", "dagDir"), data, config, headers )
        #startDagPB( dagDir, data["referenceNumber"] )
        #s = Template(EMAIL_STARTING_TEMPLATE)
        #data['description'] += "\n\n%s" % s.substitute(date=str(datetime.now()))
        #updateStatus( data, "starting", config, headers )
    # else Reservation is starting
    elif site['status'] == 'starting': 
      logging.info( "   Checking status of reservation " )
      dagDir = os.path.join( config.get("Server", "dagDir"), "dag-" + data["referenceNumber"] )
      #info = isDagRunning( dagDir, data["referenceNumber"] )
      #if info:
      #  logging.info( "   Reservation is running" )
      #  data['description'] += "\n\n%s" % info
      #  updateStatus( data, "running", config, headers ) 
    # else Reservation is running
    elif ( site['status'] == 'running' and endDiff.total_seconds() > reservationSecsLeft ):
      # <insert pcc check to make sure is true>
      shutdownTime = endDiff.total_seconds() - reservationSecsLeft
      logging.debug( "  Reservation scheduled to be shut down in %s or %d secs" % (str(endDiff), shutdownTime) )
    # else Reservation is running and needs to be shut down
    elif ( site['status'] == 'running' and endDiff.total_seconds() <= reservationSecsLeft ):
      logging.debug( "  Reservation has expired; shutting down cluster" )
      #s = Template(EMAIL_STOPPING_TEMPLATE)
      #data['description'] += "\n\n%s" % s.substitute(date=str(datetime.now()))
      #updateStatus(data, "stopping",config, headers )
      #dagDir = os.path.join( config.get("Server", "dagDir"), "dag-" + data["referenceNumber"] )
      #if stopDagPB(dagDir, data["referenceNumber"]):
      #  s = Template(EMAIL_STOPPED_TEMPLATE)
      #  data['description'] += "\n\n%s" % s.substitute(date=str(datetime.now()))
      #  updateStatus( data, "created", config, headers ) 
    # else reservation is active/future and unknown state
    else:
      logging.debug( "  Reservation in unknown state to PCC" )

