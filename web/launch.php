<?php
/**
 * launch.php:  Provide form for user to submit cluster request
 *
 * Currently only display local repository information and
 * one cluster.
 *
 * TODO: Display images from cloudfront/s3 if provided
 * 
 * TODO: Get resource options from condor
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
<script>
  $(function() {
    /* don't display button until resource is loaded */
    $("#addtoclusterbutton").hide();

    /* 
    * Loads image description when clicked and copy image name down to Step 3
    */
    $( "#select-image" ).selectable({
      stop: function() {
        var description = $( "#selected-image-description" ).empty();
        $( ".ui-selected", this ).each(function() {
          description.load("list.php?attr=image&arg=" + $(this).text() );
          $( "#selected-image-name" ).text( $(this).text() ); 
          $( "#confirmed-image-name" ).text( $(this).text() );
        });
      }
    });

    /* 
    * Loads resource description when clicked 
    */
    $( "#select-resource" ).selectable({
      stop: function() {
        var resource = $( "#selected-resource-name" ).empty();
        var description = $( "#selected-resource-description" ).empty();
        $( ".ui-selected", this ).each(function() {
          description.load("list.php?attr=resource&arg=" + $(this).text() );
          resource.append( $(this).text() ); 
          $("#addtoclusterbutton").show();
        });
      }
    });

    /* 
    * Copies selected resource name and count to Step 3 for confirmation 
    */
    $( "#addtocluster" ).submit(function( event ) {
      var cores =  $( "#cores option:selected" ).val();
      var resource = $( "#select-resource" ).text();
      $( "#confirmed-resource-spec" ).text( resource + ", " + cores + " cores" );
      event.preventDefault();
    });

    /* 
    * Submits job request to condor
    */
    $( "#submitcluster" ).submit(function( event ) {
      var selectedImage = $( "#confirmed-image-name" ).text();
      var selectedResourceSpec = $( "#confirmed-resource-spec" ).text();
      if ( selectedImage == 'None' ) {
        alert( "Error:  missing image, please select a virtual cluster image." );
      } else if ( selectedResourceSpec == 'None' ) {
        alert( "Error:  missing resource, please select a resource and # of cores." );
      } else {
        var selectedResourceParts = selectedResourceSpec.split(", ");
        var panel = $( "#submit-cluster-panel" ).empty();
        panel.load("submit.php?image=" + selectedImage + "&resource=" + encodeURIComponent(selectedResourceSpec) );
      }
      event.preventDefault();
    });
  });

  </script>
  <style>
  #feedback { font-size: 1em; }
  #select-image .ui-selecting { background: #FECA40; }
  #select-image .ui-selected { background: #DD862A; color: white; }
  #select-image { list-style-type: none; margin: 0; padding: 0; width: 10em; }
  #select-image li { margin: 3px; padding: 0.4em; font-size: 1em; height: 18px; }

  #select-resource .ui-selecting { background: #FECA40; }
  #select-resource .ui-selected { background: #F39814; color: white; }
  #select-resource { list-style-type: none; margin: 0; padding: 0; width: 250px; }
  #select-resource li { margin: 3px; padding: 1px; float: left; width: 150px; height: 80px; font-size: 1.5em; text-align: center; }
  </style>
<h1 class="pheader">Launch a Virtual Cluster</h1>
<br/>
<br/>
<table width="100%" border="0" >
 <tr><td colspan="2" align="left"><span class="psubheader">Step 1: Select an Image</span></td></tr>
 <tr><td valign="top" width="10em" style="padding: 5px">
   <ol id="select-image">
   <?php
     exec($pcc["VC_PATH"] . " -j list image", $output, $return);
     $vc_db = json_decode($output[0]);
     foreach ($vc_db as $key=>$value) {
       print " <li class=\"ui-widget-content\">" . $key . "</li>";
     }
   ?>
   </ol>
 </td>
 <td valign="top" style="padding: 5px">
   <p id="feedback">
     <center><span class="psubsubheader" id="selected-image-name">None</span></center> 
     <br/> 
     <span id="selected-image-description">Click on image name to the right to display description.</span>
   </p>
 </td></tr>
</table>
<br/><br/>
<table width="100%" border="0" >
  <tr><td colspan="2" align="left"><span class="psubheader">Step 2: Select a Resource</span></td></tr>
  <tr><td valign="top" width="20em" style="padding: 5px">
    <ol id="select-resource">
    <?php
        exec($pcc["VC_PATH"] . " -j list resource", $resource_out, $return);
        $resource_db = json_decode($resource_out[0]);
        foreach ($resource_db as $key=>$value) {
          print " <li class=\"ui-state-default\">" . $key . "</li>";
        }
    ?>
   </ol>
  </td>
  <td valign="top" style="padding: 5px">
    <p id="feedback">
      <form id="addtocluster">
        <center><span class="psubsubheader" id="selected-resource-name">None</span></center> 
        <br/> 
        <span id="selected-resource-description">Click on resource name to the right to display description.</span>
        <br/>
        <br/>
        <span id="select-resource-num"></span>
        <input type="submit" id="addtoclusterbutton" value="Add to virtual cluster">
      </form>
    </p>
  </td></tr>
</table>
<br/>
<table width="100%" border="0" >
  <tr><td align="left"><span class="psubheader">Step 3: Submit Virtual Cluster Job Request</span></td></tr>
  <tr><td> 
    <form id="submitcluster">
    <br/>
      <span class="emphasize">Image selected:</span>  <span id="confirmed-image-name">None</span>
      <br/><br/>
      <span class="emphasize">Resource selected:</span> <span id="confirmed-resource-spec">None</span>
      <br/>
      <br/>
      <span id="submit-cluster-panel"><input type="submit" id="submit-cluster-button" value="Submit virtual cluster"></span>
    </form>
  </td></tr>
</table>
 
 
