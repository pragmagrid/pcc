<?php
/**
 * scanlog.php:  Temporary PHP to read status of pragma_boot launch
 *
 * Scans temporary job directories (assumed running on exec host)
 * and reads log file and estimates progress (% complete).
 *
 * PHP version 5
 *
 * LICENSE: <insert here>
 *
 * @package    PCC
 * @author     Shava Smallen <ssmallen@sdsc.edu>
 */

  $files = scandir ( "/tmp" );
  $log = "";
  foreach ($files as &$line) {
    if ( preg_match("/^([0-9]+\.[0-9]+)$/", $line, $matches) ) {
      $log = $matches[1] . "/pragma_boot.log";
    }
  }
  $handle = fopen("/tmp/" . $log, "r");
  if ($handle) {
    $lastline = "";
    $i = 0;
    $pb_progress = 0;
    $pb_description = "";
    $num_nodes = 0;
    $frontend_boot = 1;
    $cluster = "";
    while (($line = fgets($handle)) !== false) {
      $i += 1;
      if ( preg_match( "/fix_images/", $line) ) {
        $pb_progress= 1;
        $pb_description = "Preparing images...";
      } else if ( preg_match( "/kvm_rocks\/allocate/", $line) ) {
        $pb_progress= 16;
        $pb_description = "Configuring network...";
      } else if ( preg_match( "/numnodes=/", $line) ) {
        preg_match( "/(\d+)/", $line, $matches );
        $num_nodes = $matches[0];
      } else if ( preg_match( "/fe-name=/", $line) ) {
        preg_match( "/fe-name=(\S+)/", $line, $matches );
        $cluster = $matches[1];
      } else if ( preg_match( "/Executing.*kvm_rocks\/boot/", $line) ) {
        if ( $frontend_boot ) {
          $pb_progress = 18;
          $frontend_boot = 0;
        } else {
          $pb_progress += (82 / ($num_nodes + 1));
        }
        $lineparts = preg_match_all( "/'([^']+)'/", $line, $matches );
        $pb_description = "Booting " . $matches[0][2] . "...";
      } else if ( preg_match( "/pragma_boot complete/", $line) ) {
        $pb_progress= 100;
        $pb_description = "Completed boot of " . $cluster;
      } 
    }
    print $pb_progress . " " . $pb_description;
  } else {
    // error opening the file.
  }
?>

