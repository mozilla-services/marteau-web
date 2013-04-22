<%inherit file="base.mako"/>

<script src="/media/socket.io.js"></script>


<div class="actions">
 <table class='nodes'>
  <tr>
    <th>Status</th>
    <td id="status">${status}</td>
  </tr>
  <tr>
    <th>Created</th>
    <td>${time2str(job.metadata.get('created'))}</td>
  </tr>
  %if 'started' in job.metadata:
 <tr>
    <th>Started</th>
    <td>${time2str(job.metadata.get('started'))}</td>
  </tr>
  %endif
  %if 'ended' in job.metadata:
  <tr>
    <th>Ended</th>
    <td>${time2str(job.metadata.get('ended'))}</td>
  </tr>
   %endif
 </table>
</div>

<div class="actions" id="actions">
  %if report:
  <a id="report" class="label" href="/report/${job.job_id}/index.html">Report</a>
  %endif
  %if 'ended' in job.metadata:
  <a id="delete" class="label" href="/test/${job.job_id}/delete">Delete</a>
  <a id="replay" class="label" href="/test/${job.job_id}/replay">Replay</a>
  %endif
</div>


<div style="clear: both"/>

<div style="padding-top: 5px; padding-left: 20px; padding-right: 20px; background-color: black; color: white">
 Marteau Console for Job ${job.job_id}
</div>
<div id="console" style="overflow-x:hidden; overflow-y:scroll;padding-bottom: 20px;font-family: monospace;white-space: pre;padding-left: 20px; padding-right: 20px; background-color: black; color: white;
max-height: 500px">
Waiting for data...
</div>
<div style="padding-left: 20px; padding-right: 20px; background-color: black; color: white">
  <blink>...</blink>
</div>
<script type="text/javascript">
$(document).ready(function() {
  // connect to the websocket
  var socket = io.connect();

  socket.emit("subscribe", 'console.${job.job_id}');

  socket.on("console.${job.job_id}", function(line) {

    if (line.startsWith("END.")) {

      var status = line.split("END.")
      status = status[1];
      $('#status').text(status);

      if (status == "Success") {
       $("#actions").prepend('<a id="report" class="label" href="/report/${job.job_id}/index.html">Report</a>\n');
      }

     if (!$('#delete').length) { 
         $("#actions").prepend('<a id="delete" class="label" href="/test/${job.job_id}/delete">Delete</a>\n');
     }

     if (!$('#replay').length) { 
       $("#actions").prepend('<a id="replay" class="label" href="/test/${job.job_id}/replay">Replay</a>\n');
     }
    }
    else {
      $('#console').append(line);
      $("#console").scrollTop($("#console")[0].scrollHeight);
   }
  });



});
</script>
