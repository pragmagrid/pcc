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
from email.mime.text import MIMEText
import glob
from httplib import HTTPSConnection
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
from string import Template
import socket
import smtplib
import ssl
import subprocess
import sys
import time
import urllib

ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
ISO_LENGTH = 19

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
--mem             = $mem
--vcname          = $vcname
--logfile         = $jobdir/pragma_boot.log
"""
# --enable-ipop-server=http://nbcr-224.ucsd.edu/ipop/exchange.php?jobId=$jobid

RESERVATION_TEMPLATE = """Dear $userFirst,

Your PRAGMA Cloud reservation has been updated.  Please see details below.

Reservation:

ID:          $reservation_id
Title:       $title
Description: $description
Begin Time:  $begin
End Time:    $end
VC Image:    $image

Sites ($numsites):
"""

SITE_TEMPLATE = """
  Site: $siteName
    Status: $status
    CPUs:   $cpus
    Memory: $memory
    $notes
"""

LOGIN_INFO = """

    You may now log into the frontend.  E.g.,

    # ssh root@$fqdn
"""


class GUIClient:
  def __init__(self, config):
    self.host = config.get("Server", "hostname")
    self.username = config.get("Authentication", "username")
    self.password = config.get("Authentication", "password")
    self.base_url = config.get("Server", "baseUrl")
    self.session_id = None

  def authenticate(self):
    logging.info("Authenticating to Cloud GUI")
    connection = HTTPSConnection(
      self.host, context=ssl._create_unverified_context())
    connection.connect()

    creds = {"username": self.username, "password": self.password}
    auth_url = "%s/signIn.py" % self.base_url
    session = self._run_query(connection, auth_url, "POST", creds)
    self.session_id = session["session_id"]
    connection.close()

  def _run_query(self, connection, path, method, params):
    """
    Send a REST API request

    Args:
      connection(HTTPConnection): An already open HTTPConnection
      path(string): REST API path function
      method(string): POST or GET
      params(string): Arguments to REST function

    Returns:
      JSON object: response from server
    """
    connection.request(method, path, urllib.urlencode(params))
    response = connection.getresponse()
    if response.status != 200:
      sys.stderr.write("Problem querying " + path + ": " + response.reason)
      sys.stderr.write(response.read())
      sys.exit(1)
    responsestring = response.read()
    return json.loads(responsestring)

  def query(self, function, method, params):
    """Send a GUI API request

      Args:
        config(ConfigParser): Config file input data
        function(string): Name of Booked REST API function
        method(string): POST or GET
        params(string): Arguments to REST function

      Returns:
        dict: contains Booked auth info
        JSON object: response from server
    """
    connection = HTTPSConnection(self.host, context=ssl._create_unverified_context())
    connection.connect()

    if not params:
      params = {}
    params['session_id'] = self.session_id

    url = "%s/%s" % (self.base_url, function)
    logging.debug("  Sending API call: " + url)
    data = self._run_query(connection, url, method, params)
    connection.close()
    return data

  def query_site(self, params):
    responsedata = self.query("GetSiteDescription.py", "POST", params)
    if 'site' in responsedata:
      return responsedata['site']
    else:
      return None

  def update_status(self, reservation, site, new_status, description=None):
    """Send reservation update request

      Args:
        reservation(dict): details of reservation
        site(dict): details of reservation site
        new_status(string): new status for reservation
        config(ConfigParser): Config file input data

      Returns:
        bool: True if successful, False otherwise.
    """
    params = {
      'status': new_status,
      'session_id': self.session_id,
      'reservation_id': reservation['reservation_id'],
      'site_id': site['site_id']
    }
    if description:
      params['description'] = description
    responsedata = self.query("updateReservationStatus.py", "POST", params)
    logging.debug("  Server response was: " + responsedata['result'])
    if responsedata['result'] == 'True':
      return True, responsedata['reservation']
    else:
      return False, reservation


class Reservation:
  WORKFLOW = {
    'waiting': 'created',
    'created': 'starting',
    'starting': 'running',
    'cancel': 'stopped',
    'running': 'stopped',
    'stopping': 'stopping',
    'stopped': 'stopped'
  }

  def __init__(self, reservation, user, dag_dir, client):
    self.client = client
    self.reservation = reservation
    self.user = user

    logging.info("Reservation: ref=%s" % reservation["reservation_id"])
    start = datetime.strptime(reservation['begin'][:ISO_LENGTH], ISO_FORMAT)
    end = datetime.strptime(reservation['end'][:ISO_LENGTH], ISO_FORMAT)
    now = datetime.utcnow()
    logging.info(
      "  Start: %s, End %s" % (reservation['begin'], reservation['end']))
    self.start_diff = start - now
    self.end_diff = end - now
    self.shutdown_secs = int(config.get("Stopping", "reservationSecsLeft"))

    self.params = {
      'reservation_id': reservation['reservation_id']
    }
    self.dag = Dag(dag_dir, reservation['reservation_id'])
    self.client = client

  def handle_reservation_site(self, site):
    target_status = Reservation.WORKFLOW[site['status']]
    logging.info("  Site %s, status=%s" % (site['site_name'], site['status']))
    logging.info("  Calling reservation handle function '%s'" % target_status)
    self.params['site_id'] = site['site_id']
    site_desc = self.client.query_site(self.params)
    handle_func = getattr(self, target_status)
    if handle_func:
      (success, desc) = handle_func(site, site_desc)
      if success:
        (update_result, self.reservation) = self.client.update_status(
          self.reservation, site, target_status, desc)
        if update_result:
          return target_status, self.reservation
    else:
      logging.debug("  Reservation in unknown state to PCC")
    return site['status'], self.reservation

  def created(self, site, site_desc):
    return True, None

  def starting(self, site, site_desc):
    logging.debug("  Reservation should be started in: " + str(self.start_diff))
    if self.start_diff.total_seconds() <= 0:  # should be less than
      logging.info("   Starting reservation at " + str(datetime.utcnow()))
      self.dag.write(reservation, userdata, site, site_desc)
      self.dag.start()
      return True, None
    return False, None

  def running(self, site, site_desc):
    logging.info("   Checking status of reservation ")
    info = self.dag.is_running()
    if info:
      logging.info("   Reservation is running")
      return True, info
    return False, None

  def stopped(self, site, site_desc):
    if site['status'] == 'stopped':  # already stopped
      return False, None
    elif self.end_diff.total_seconds() > self.shutdown_secs:
      # <insert pcc check to make sure is true>
      shutdownTime = self.end_diff.total_seconds() - self.shutdown_secs
      logging.debug(
        "  Reservation scheduled to be shut down in %s or %d secs" % (
          str(res.end_diff), shutdownTime))
      return False, None
    else:
      logging.info("  Reservation has expired; shutting down cluster")
      self.client.update_status(self.reservation, site, "stopping", "--")
      if self.dag.stop():
        return True, "--"
    return False, None

  def stopping(self, site, site_desc):
    pass


class Dag:

  def __init__(self, dag_dir, reservation_id):
    self.dag_dir = os.path.join(dag_dir, "dag-%s" % reservation_id)
    self.reservation_id = reservation_id

  def _run_shell_command(self, cmd, stdout_filename):
    """Run bash shell command

      Args:
        stdout_filename: put stdout in specified filename

      Returns:
        exit code of cmd
    """

    stdout_f = open(stdout_filename, "w")
    result = subprocess.call(cmd, stdout=stdout_f, shell=True)
    stdout_f.close()

    f = open(stdout_filename, "r")
    stdout_text = f.read()
    f.close()
    return (result, stdout_text)


  def write(self, reservation, user, site, site_desc):
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
    # make dag dir and write user's key to disk
    if not os.path.exists(self.dag_dir):
      logging.debug("  Creating dag directory " + self.dag_dir)
      os.makedirs(self.dag_dir)
      rf = open('/root/.ssh/id_rsa.pub', 'r')
      root_key = rf.read()
      rf.close()
      sshKeyPath = os.path.join(self.dag_dir, "public_key")
      f = open(sshKeyPath, 'w')
      logging.debug("  Writing file " + f.name)
      f.write(user['public_key'] + "\n")
      f.write("%s\n" % root_key)
      f.close()

    # write dag file
    dag_f = open(os.path.join(self.dag_dir, "dag.sub"), 'w')
    logging.debug("  Writing file " + dag_f.name)

    # create dag node files for each resource in reervation
    dagNodeDir = os.path.join(self.dag_dir, "vc%s" % site["site_id"])
    if not os.path.exists(dagNodeDir):
      logging.debug("  Creating dag node directory " + dagNodeDir)
      os.mkdir(dagNodeDir)
      # get resource info
      f = open(os.path.join(dagNodeDir, "vc%s.sub" % site["site_id"]), 'w')
      logging.debug("  Writing file " + f.name)
      dag_f.write(" JOB VC%s  %s\n" % (site["site_id"], f.name))
      s = Template(NODE_TEMPLATE)
      # optional params
      python_path = "" if site_desc['python_path'] is None else site_desc[
        'python_path']
      f.write(s.substitute(id=site["site_id"], host=site_desc['site_hostname'],
                           pragma_boot_path=site_desc['pragma_boot_path'],
                           python_path=python_path,
                           version=site_desc['pragma_boot_version'],
                           username=site_desc['username'],
                           var_run=site_desc['temp_dir'], memory=site['memory'],
                           jobdir=self.dag_dir))
      f.close()
      f = open(os.path.join(dagNodeDir, "vc%s.vmconf" % site["site_id"]), 'w')
      logging.debug("  Writing file " + f.name)
      s = Template(VMCONF_TEMPLATE)
      f.write(s.substitute(cpus=site['CPU'], vcname=reservation['image_type'],
                           sshKeyPath=sshKeyPath, jobdir=self.dag_dir,
                           jobid=os.getpid(), mem=site['memory']))
      f.close()

    # close out dag file
    dag_f.close()

  def is_running(self):
    """Check to see if dag is running

      Args:
        dagDir(string): Path to directory to store Condor DAGs

      Returns:
        bool: True if dag is running, False otherwise.
    """
    (active, inactive, resourceinfo, frontendFqdn) = ([], [], "", "")
    subf = open(os.path.join(self.dag_dir, 'dag.sub'), 'r')
    for line in subf:
      matched = re.match(".*\s(\S+)$", line)
      if matched:
        vcdir = os.path.dirname(matched.group(1))
        hostname = getRegexFromFile(os.path.join(vcdir, "hostname"), "(.*)")
        [conf] = glob.glob(os.path.join(vcdir, "*.sub"))
        username = getRegexFromFile(conf, "username\s*=\s*(.*)")
        var_run = getRegexFromFile(conf, "var_run\s*=\s*(.*)")
        pragma_boot_path = getRegexFromFile(conf, "pragma_boot_path\s*=\s*(.*)")
        python_path = getRegexFromFile(conf, "python_path\s*=\s*?(\S*?)$")
        pragma_boot_version = getRegexFromFile(conf,
                                               "pragma_boot_version\s*=\s*(.*)")
        remote_dag_dir = os.path.join(var_run, "dag-%s" % self.reservation_id)
        if pragma_boot_version == "2":
          scp = 'scp %s@%s:%s %s >& /dev/null' % (
            username, hostname, os.path.join(remote_dag_dir, "pragma_boot.log"),
            vcdir)
          logging.debug("  %s" % scp)
          subprocess.call(scp, shell=True)
          frontend = getRegexFromFile(
            os.path.join(vcdir, "pragma_boot.log"), 'Allocated cluster (\S+)')
          if not frontend:
            frontend = getRegexFromFile(os.path.join(vcdir, "pragma_boot.log"),
                                        'Successfully deployed frontend (\S+)')
          ssh = 'ssh %s@%s %s %s/bin/pragma list cluster %s' % (
            username, hostname, python_path, pragma_boot_path, frontend)
          pragma_status_filename = os.path.join(vcdir, "pragma_list_cluster")
          stdout_f = open(pragma_status_filename, "w")
          logging.debug("  %s" % ssh)
          result = subprocess.call(ssh, stdout=stdout_f, shell=True)
          stdout_f.close()
          f = open(pragma_status_filename, "r")
          status = f.readlines()
          f.close()
          status.pop(0)  # discard header
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
            ssh = 'echo | nc -w 30 %s 22 2>&1 | grep SSH > /dev/null 2>&1' % (
              publicIP)
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
          logging.error(
            "Error, unknown or unsupported pragma_boot version %s" % pragma_boot_version)
          sys.exit(1)
    logging.info("   Active clusters: %s" % str(active))
    logging.info("   Inactive clusters: %s" % str(inactive))
    subf.close()
    if len(inactive) == 0:
      s = Template(LOGIN_INFO)
      return s.substitute(fqdn=publicIP)
    return None


  def start(self):
    """Start the dag using pragma_boot directly via SSH

      Returns:
        bool: True if writes successful, False otherwise.
    """
    local_hostname = socket.gethostname()
    subf = open(os.path.join(self.dag_dir, 'dag.sub'), 'r')
    for line in subf:
      matched = re.match(".*\s(\S+)$", line)
      if matched:
        vcfile = matched.group(1)
        hostname = getRegexFromFile(vcfile, 'Machine =="([^"]+)"')
        username = getRegexFromFile(vcfile, "username\s*=\s*(.*)")
        pragma_boot_path = getRegexFromFile(vcfile,
                                            "pragma_boot_path\s*=\s*(\S+)")
        python_path = getRegexFromFile(vcfile, "python_path\s*=\s*?(\S*?)$")
        pragma_boot_version = getRegexFromFile(vcfile,
                                               "pragma_boot_version\s*=\s*(\S+)")
        var_run = getRegexFromFile(vcfile, "var_run\s*=\s*(\S+)")
        remote_dag_dir = os.path.join(var_run, "dag-%s" % self.reservation_id)

        host_f = open(os.path.join(os.path.dirname(vcfile), "hostname"), 'w')
        host_f.write(hostname)
        host_f.close()
        if hostname != local_hostname:
          logging.debug(
            "  Copying dir %s over to %s:%s " % (self.dag_dir, hostname, remote_dag_dir))
          subprocess.call('ssh %s@%s mkdir -p %s' % (username, hostname, var_run),
                          shell=True)
          subprocess.call('scp -r %s %s@%s:%s >& /dev/null' % (
            self.dag_dir, username, hostname, remote_dag_dir), shell=True)
        vmconf_file = vcfile.replace('.sub', '.vmconf')
        vmf = open(vmconf_file, 'r')
        if pragma_boot_version == "2":
          args = {}
          for line in vmf:
            matched = re.match("--(\S+)\s+=\s+(\S+)", line)
            args[matched.group(1)] = matched.group(2)
          # pragma_boot takes memory per node so divide memory by num nodes (computes + frontend)
          mem_per_node = 1024 * round(int(args["mem"]) / (int(args["num_cpus"]) + 1.0))
          args["key"] = args["key"].replace(self.dag_dir, remote_dag_dir)
          args["logfile"] = args["logfile"].replace(self.dag_dir, remote_dag_dir)
          cmdline = "ssh -f %s@%s 'cd %s; %s %s/bin/pragma boot %s %s key=%s loglevel=DEBUG logfile=%s mem=%i' >& %s/ssh.out" % (
            username, hostname, remote_dag_dir, python_path, pragma_boot_path,
            args["vcname"], args["num_cpus"], args["key"], args["logfile"],
            mem_per_node, self.dag_dir)
        else:
          logging.error(
            "Error, unknown or unsupported pragma_boot version %s" % pragma_boot_version)
          sys.exit(1)
        logging.debug("  Running pragma_boot: %s" % cmdline)
        subprocess.call(cmdline, shell=True)
    subf.close()
    logging.debug("  Sleeping 10 seconds")
    time.sleep(10)
    return True

  def stop(self):
    """Stop the dag using pragma_boot directly via SSH

      Returns:
        bool: True if writes successful, False otherwise.
    """
    local_hostname = socket.gethostname()
    subf = open(os.path.join(self.dag_dir, 'dag.sub'), 'r')
    for line in subf:
      matched = re.match(".*\s(\S+)$", line)
      if matched:
        vcfile = matched.group(1)
        vcdir = os.path.dirname(matched.group(1))
        hostname = getRegexFromFile(vcfile, 'Machine =="([^"]+)"')
        username = getRegexFromFile(vcfile, "username\s*=\s*(.*)")
        pragma_boot_path = getRegexFromFile(vcfile,
                                            "pragma_boot_path\s*=\s*(\S+)")
        python_path = getRegexFromFile(vcfile, "python_path\s*=\s*?(\S*?)$")
        frontend = getRegexFromFile(os.path.join(vcdir, "pragma_boot.log"),
                                    'Allocated cluster (\S+)')
        ssh_pragma = "ssh %s@%s %s %s/bin/pragma" % (
          username, hostname, python_path, pragma_boot_path)
        shutdown_cmd = "%s shutdown %s" % (ssh_pragma, frontend)
        logger.debug("  Shutting down %s: %s" % (frontend, shutdown_cmd))
        (result, stdout_text) = self._run_shell_command(
          shutdown_cmd, os.path.join(vcdir, "pragma_shutdown"))
        if result != 0:
          logger.error("  Error shutting down virtual cluster %s" % frontend)
          return False
        logger.debug("  %s" % stdout_text)
        clean_cmd = "%s clean %s" % (ssh_pragma, frontend)
        logger.debug("  Cleaning %s: %s" % (frontend, clean_cmd))
        (result, stdout_text) = self._run_shell_command(
          clean_cmd, os.path.join(vcdir, "pragma_clean"))
        logger.debug("  %s" % stdout_text)
        if result != 0:
          logger.error("  Error cleaning virtual cluster %s" % frontend)
          return False
    return True


def getRegexFromFile(file, regex):
  """Grab some strings from a file based on a regex

    Args:
      file(string): Path to file containing string
      regex(string): Regex to parse from file

    Returns:
      list: Args returned from regex
  """
  f = open(file, "r")
  matcher = re.compile(regex, re.MULTILINE)
  matched = matcher.search(f.read())
  f.close()
  if not matched:
    return []
  elif len(matched.groups()) == 1:
    return matched.group(1)
  else:
    return matched.groups()


def writeStringToFile(file, aString):
  """Write a string to file

    Args:
      file(string): Path to file containing string
      aString(string): string to write to file

    Returns:
      bool: True if success otherwise false
  """
  f = open(file, 'w')
  f.write(aString)
  return f.close()

# main

# read input arguments from property file
config = ConfigParser()
config.read("cloud-scheduler.cfg");

# configure logging 
logger = logging.getLogger()
logger.setLevel(config.get("Logging", "level"))
handler = TimedRotatingFileHandler(config.get("Logging", "file"), when="W0",
                                   interval=1, backupCount=5)
handler.setFormatter(logging.Formatter(
  "%(asctime)s - %(levelname)s - line %(lineno)d - %(message)s"))
logger.addHandler(handler)

client = GUIClient(config)
client.authenticate()

# Examine all reservations and determine which require actions
logging.debug("Reading current and future reservations")
data = client.query("pccGetAllReservations.py", "POST", None)

site_descriptions = {}

# Iterate thru unique reservations
for reservation in data["result"]:
  userparams = {'username': reservation['owner']}
  userdata = client.query("getUserData.py", "POST", userparams)
  res = Reservation(reservation, userdata, config.get("Server", "dagDir"), client)

  site_status_changes = {}
  for site in reservation["sites"]:

    site_was_status = site['status']
    try:
      site_now_status, res_update = res.handle_reservation_site(site)
      if res_update:
        reservation = res_update
      if site_now_status is not None and site_now_status != site_was_status:
        site_status_changes[site['site_id']] = {
          'was': site_was_status, 'now': site_now_status}
    except Exception as e:
      logging.exception("  Error processing reservation: %s" % res.reservation['reservation_id'])

  if site_status_changes:
    s = Template(RESERVATION_TEMPLATE)
    mailbody = s.substitute(userFirst=userdata['firstname'].capitalize(),
                            reservation_id=reservation['reservation_id'],
                            title=reservation['title'],
                            description=reservation['description'],
                            begin=reservation['begin'], end=reservation['end'],
                            image=reservation['image_type'],
                            numsites=len(reservation['sites']))
    for site in reservation["sites"]:
      notes = ""
      if site['admin_description'] != 'None':
        notes = "Admin notes: %s" % site['admin_description']
      s = Template(SITE_TEMPLATE)
      site_status = site_status_changes[site['site_id']]['was']
      if site_status_changes[site['site_id']]['now']:
        site_status = "%s (was %s)" % (
          site_status_changes[site['site_id']]['now'],
          site_status_changes[site['site_id']]['was'])
      mailbody += s.substitute(siteName=site['site_name'], status=site_status,
                               cpus=site['CPU'], memory=site['memory'],
                               notes=notes)

    msg = MIMEText(mailbody)
    msg['Subject'] = 'Update: PRAGMA Cloud Scheduler reservation #%s' % \
                     reservation['reservation_id']
    msg['From'] = 'root@%s' % config.get("Server", "hostname")
    msg['To'] = userdata['email_address']

    s = smtplib.SMTP('localhost')
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()
