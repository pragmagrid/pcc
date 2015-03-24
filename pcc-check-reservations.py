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
import os
from string import Template
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
rocks_should_transfer_files = Yes
RunAsOwner=True
queue
"""

VMCONF_TEMPLATE = """--executable      = pragma_boot
--basepath        = /opt/pragma_boot/vm-images
--key             = $sshKeyPath
--num_cpus       = $cpus       
--vcname          = $vcname
--logfile         = $jobdir/pragma_boot.log
--enable-ipop-server=http://$${COLLECTOR_HOST_STRING}/ipop/exchange.php?jobId=$${DAGManJobId}
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
      bool: True if writes successful, False otherwise.
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
  sshKeyPath = os.path.join(dagDir, "public_key")
  f = open( sshKeyPath, 'w' )
  logging.debug( "  Writing file " + f.name );
  f.write(userAttrs['SSH public key'] + "\n");
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
    f.write(s.substitute(id=resource["id"], host=resourceAttrs['Site hostname'], memory=reservAttrs['Memory (Gb/host)'], jobdir=dagDir))
    f.close()
    f = open(os.path.join(dagNodeDir,"vc"+resource["id"]+".vmconf"), 'w')
    logging.debug( "  Writing file " + f.name );
    s = Template(VMCONF_TEMPLATE)
    f.write( s.substitute(cpus=reservAttrs['CPU (per host)'], vcname=reservAttrs['VC Name'], sshKeyPath=sshKeyPath, jobdir=dagDir) )
    f.close()

  # close out dag file
  dag_f.close()
  return True


# read input arguments from property file
config = ConfigParser()
config.read("cloud-scheduler.cfg");
reservationSecsLeft = int( config.get( "Stopping", "reservationSecsLeft" ) );

# configure logging 
logging.basicConfig(
  filename=config.get("Logging", "file"), 
  format='%(asctime)s %(levelname)s:%(message)s', 
  level=config.get("Logging", "level")
)

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
      writeDag( config.get("Server", "dagDir"), data, config, headers )
      if not( updateStatus(data, "starting", config, headers) ):
        continue
      # <insert check of pcc status and check if running yet>
      logging.info( "   VC running at " + str(datetime.now()) )
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

