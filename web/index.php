<?php
/**
 * index.php:  implements Personal Cloud Controller (PCC)
 *
 * Displays basic information on PCC and provides the ability to:
 *
 * 1) Launch new cluster jobs
 * 2) View running clusters
 *
 * PHP version 5
 *
 * LICENSE: <insert here>
 *
 * @package    PCC
 * @author     Shava Smallen <ssmallen@sdsc.edu>
 */
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PRAGMA Personal Cloud Controller</title>
  <link rel="stylesheet" href="//code.jquery.com/ui/1.10.4/themes/smoothness/jquery-ui.css">
  <script src="//code.jquery.com/jquery-1.9.1.js"></script>
  <script src="//code.jquery.com/ui/1.10.4/jquery-ui.js"></script>
  <link media="screen, projection" type="text/css" rel="stylesheet" href="css/layout.css">

  <script>
    $(function() {
      $( "#tabs" ).tabs( {cache: false} ).addClass( "ui-tabs-vertical ui-helper-clearfix" );
      $( "#tabs li" ).removeClass( "ui-corner-top" ).addClass( "ui-corner-left" );
    });
  </script>

  <style>
  .ui-tabs-vertical { width: 70em; }
  .ui-tabs-vertical .ui-tabs-nav { padding: .2em .1em .2em .2em; float: left; width: 59; }
  .ui-tabs-vertical .ui-tabs-nav li { clear: left; width: 100%; border-bottom-width: 1px !important; border-right-width: 0 !important; margin: 0 -1px .2em 0; }
  .ui-tabs-vertical .ui-tabs-nav li a { display:block; }
  .ui-tabs-vertical .ui-tabs-nav li.ui-tabs-active { padding-bottom: 0; padding-right: .1em; border-right-width: 1px; border-right-width: 1px; background: #379BBF}
  .ui-tabs-vertical .ui-tabs-panel { padding: 1em; float: right; width: 50em;}

  .pheader { color: #4E4E4E; border-bottom-style:solid; border-bottom-color:#379BBF;}
  .psubheader { color: #4E4E4E; border-bottom-style:solid; border-bottom-color:#DD862A; font-weight:bold;}
  .psubsubheader { color: #DD862A; font-weight:bold;}
  .emphasize { color: #4E4E4E; font-weight:bold; }
  .de_emphasize { color: #4E4E4E; font-size: x-small}
  </style>
</head>
<body>

<div id="wrap-container">
  <div id="wrap">
    <div id="tabs">
      <ul>
        <li><img src="images/bg-logo.png"/><p align="center">Personal Cloud Controller</p></li>
        <li><a href="#tabs-1">Introduction</a></li>
        <li><a href="launch.php">Launch a Virtual Cluster</a></li>
        <li><a href="view.php">View Virtual Clusters</a></li>
      </ul>
      <div id="tabs-1">
        <h1 class="pheader">Introduction</h1>
        <br/>
        <p>The <a href="http://www.pragma-grid.net">PRAGMA Cloud</a> is multi-provider cloud technology development testbed with sites around the Pacific Rim.  One of the goals of PRAGMA is to enable users to author their own application virtual machines (VMs) once using their preferred VM platforms and then use PRAGMA tools to easily deploy their VMs as virtual clusters (VCs) anywhere on PRAGMA sites.  </p>
      <br/>
        </p>Today, there are a number of PRAGMA tools such as <a href="https://github.com/pragmagrid/pragma_boot">pragma_boot</a>, <a href="http://ipop-project.org">iPOP</a>, etc. that provide pieces of the functionality needed to enable VCs to run anywhere on PRAGMA.  The goal of this effot is to create a lightweight VC management tool, that integrates the various PRAGMA tools with a well known resource management tool called <a href="http://research.cs.wisc.edu/htcondor/">HTCondor</a> to provide users with an easy-to-use interface for VC management.  Users will have a high degree of controllability for managing their VCs as well as access detailed status data to monitor the health of the VCs.</p>
        <br/>
      </div> <!-- tabs-1 -->
    </div> <!-- tabs -->
  </div> <!-- wrap -->
</div> <!-- wrap-container -->

</body>
</html>
