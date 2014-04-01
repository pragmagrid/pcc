<?php
/**
 * view.php:  Display status of clusters jobs
 *
 * Currently only displays status of running clusters. 
 *
 * TODO: Get status from condor once implemented
 *
 * PHP version 5
 *
 * LICENSE: <insert here>
 *
 * @package    PCC
 * @author     Shava Smallen <ssmallen@sdsc.edu>
 */
?>
<script>
  $(function() {
    /* Set height of each windown to content */
    $( "#accordion" ).accordion({
      heightStyle: "content"
    });

    /* nested accordion if we need it */
    $( "#subaccordion" ).accordion({
      heightStyle: "content"
    });
  });
</script>
<h1 class="pheader">View Virtual Clusters</h1>
<br/>
<div id="accordion">
<?php
  $pcc = parse_ini_file("pcc.ini");

  exec($pcc["VC_PATH"] . " -j qstat", $qstat, $return);
  $vcs = json_decode( $qstat[0] );
  foreach ($vcs as $key=>$value) {
    print " <h3>" . $key . "</h3>";
    print "<div>";
    $vc = $vcs->{$key};
    print "<p>Status:  " . $vc->{'STATUS'} . "</p>";
    print "<p>Client Nodes:  ";
    if ( ! array_key_exists("CLIENT NODES", $vc) ) {
      print "None";
      continue; 
    }
    print "</p>";
    foreach ($vc->{"CLIENT NODES"} as $key=>$value) {
      $node = $vc->{"CLIENT NODES"};
      print "<p>&nbsp; &nbsp;" . $key . ":  " . $node->{$key}->{"STATUS"} . "</p>";
    }
    print "</div>";
  }
?>
</div>
<br/>
<p class="de_emphasize">
<?php 
  date_default_timezone_set( $pcc["TIMEZONE"] );
  print "Status loaded at: " .  date("r") . "<br/>"; 
?>
</p>
