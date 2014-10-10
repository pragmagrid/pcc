<?php
/**
 * submit.php:  Submit job request and display status of request
 *
 * Submits request to Condor and displays progressbar until cluster
 * is booted.
 *
 * TODO: Get progress from Condor
 * 
 * PHP version 5
 *
 * LICENSE: <insert here>
 *
 * @package    PCC
 * @author     Shava Smallen <ssmallen@sdsc.edu>
 */

  $pcc = parse_ini_file("pcc.ini");
?>
<style>
  .ui-progressbar {
    position: relative;
  }
  .progress-label {
    position: absolute;
    left: 50%;
    top: 4px;
    font-weight: bold;
    text-shadow: 1px 1px 0 #fff;
  }
</style>
<script>
  $(function() {
    /*
    * Load content from server and return content
    */
    function getString(url) {
      return $.ajax({
        type: 'GET',
        url: url,
        dataType: 'string',
        global: false,
        async:false,
        success: function(data) {
          return data;
        }
      }).responseText;
    }
 
    /*
    * Read progress of launch from file (scanlog.php)
    */
    function progress() {
      var val = progressbar.progressbar( "value" ) || 0;
      var logSummary = getString('scanlog.php');
      var lines = logSummary.match(/([\d\.]+)(.*)/); 
      var percent_complete = parseInt( lines[1] );
      progressbar.progressbar( "value", percent_complete );
      var bar_description = $( "#progressbar-description" ).empty();
      bar_description.text( lines[2] );
      var elapsed_description = $( "#elapsed" ).empty();
      var elapsed = ($.now() - startTime) / 60000;
      elapsed_description.text( elapsed.toFixed(2).toString() + " minutes");
      if ( val < 99 ) {
        setTimeout( progress, 5000 );
      }
    }

    var progressbar = $( "#progressbar" );
    progressLabel = $( ".progress-label" );
    var startTime = $.now();

    progressbar.progressbar({
      value: false,
      change: function() {
        progressLabel.text( progressbar.progressbar( "value" ) + "%" );
      },
      complete: function() {
        progressLabel.text( "Complete!" );
      }
    });

    setTimeout( progress, 10000 );
  });
</script>

<?php
  date_default_timezone_set( $pcc["TIMEZONE"] );
  preg_match("/, ([0-9]+)/", $_GET['resource'], $matches);
  $cores = $matches[1];
  $resource_spec = explode( ", ",  $_GET['resource'] );
  $submitdir = "/var/log/pcc/submit/job/" . date( "Ymd.U" . "/" );
  print "<span class=\"emphasize\">Submit time:</span> " . date("r") . "<br/><br/>";
  $old = umask(0); 
  if (!mkdir($submitdir, 0775, true)) {
    die('Failed to create folders...');
  }
  print "Created submit directory " . $submitdir . "<br/>";
  umask($old); 
  chgrp ( $submitdir, "pcc" );
  $vmconf = "executable      = pragma_boot\n";
  $vmconf .= "basepath        = /opt/pragma_boot/vm-images\n";
  $vmconf .= "key             = ~/.ssh/id_rsa.pub\n";
  $vmconf .= "num_cores       = " . $cores . "\n";
  $vmconf .= "vcname          = " .  $_GET['image'] . "\n";
  $vmconf .= "logfile         = shava_pragma_boot.log\n";
  file_put_contents($submitdir . "test.vmconf", $vmconf);
  $sub = "universe                     = vm\n";
  $sub .= "vm_type                      = rocks\n";
  $sub .= "executable                   = rocks_vm_1\n";
  $sub .= "log                          = condor.vm.log.txt\n";
  $sub .= "vm_memory                    = 64\n";
  $sub .= "rocks_job_dir                  = " . $submitdir . "\n";
  $sub .= "JobLeaseDuration             = 7200\n";
  $sub .= "RequestMemory = 64\n";
  $sub .= "rocks_should_transfer_files = True\n";
  $sub .= "queue\n";
  file_put_contents($submitdir . "condor.sub", $sub);
  chdir( $submitdir );
  exec("/usr/bin/sudo -u yuanluo /opt/vc-manager/vc-manager.py qsub condor.sub", $output, $return);
  foreach ($output as &$line) {
    print $line . "<br/>";
  }
?> 
<div id="progressbar"><div class="progress-label">Loading...</div></div>
<br/>
Progress:  <span id="progressbar-description"></span>  
<br/>
Elapsed time: <span id="elapsed"></span>
