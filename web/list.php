<script>
  $(function() {
    $( "#addtocluster" ).submit(function( event ) {
      var val =  $( "#cores option:selected" ).val();
     alert( "Button called " + val);
     event.preventDefault();
    });
  });

</script>
<?php
  exec("/opt/vc-manager/vc-manager.py list " . $_GET['attr'] . " " . $_GET['arg'], $output, $return);
  foreach ($output as &$line) {
    print $line . "<br/>";
  }
  if ($_GET['attr'] == "resource" and $_GET['arg'] != "") {
    exec("/opt/vc-manager/vc-manager.py -j list " . $_GET['attr'] . " " . $_GET['arg'], $json_output, $return);
    $resource_db = json_decode($json_output[0]);
    print "<form id=\"addtocluster\">";
    $avail_cores = $resource_db->{"total_cores"} - $resource_db->{"used_cores"};
    print "<input type=\"hidden\" id=\"avail_cores\" value=\"" . $avail_cores . "\"/>";
    print "<br/>";
    print "Select # of cores:  <select id=\"cores\"><option>" . $avail_cores. "</option></select>";
    print "<br/><br/>";
    print "<input type=\"submit\" id=\"addtocluster\" value=\"Add to virtual cluster\">";
    print "</form>";
  }
?>
