<?php
require __DIR__ . '/auth.php';
$auth = new Auth($config);
$auth->requireLogin();

// get user_id from query string
$user_id = (int)($_GET['user_id'] ?? 0);
if ($user_id <= 0) {
  header('Location: index.php');
  exit;
}
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin - User Devices</title>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<style>
  body{font-family:system-ui; margin:24px; background:#f6f7fb;}
  .card{background:#fff; border:1px solid #e7e7ef; border-radius:14px; padding:16px; margin-bottom:16px;}
  select{padding:10px 12px; border:1px solid #ddd; border-radius:10px; min-width:320px;}
  button{padding:10px 12px; border:1px solid #ddd; border-radius:10px; background:#f2f2f7; cursor:pointer;}
  table{width:100%; border-collapse:collapse;}
  th,td{padding:10px; border-bottom:1px solid #eee; text-align:left;}
  .muted{color:#666; font-size:13px;}
  .error{color:#b00020; white-space:pre-wrap;}
  a{color:#2b5cff; text-decoration:none;}
  .topbar{display:flex; justify-content:space-between; align-items:center;}
</style>
</head>
<body>

<div class="card">
  <div class="topbar">
    <div>
      <h2 style="margin:0 0 6px 0;">Assign devices</h2>
      <div class="muted">User ID: <b id="uid"><?= htmlspecialchars((string)$user_id) ?></b></div>
      <div class="muted" style="margin-top:6px;"><a href="index.php">← Back</a></div>
    </div>
    <div><a href="logout.php">Logout</a></div>
  </div>
</div>

<div class="card">
  <h3 style="margin:0 0 10px 0;">Assign a device</h3>
  <select id="sel"></select>
  <button id="btnAssign">Assign</button>
  <button id="btnRefresh">Refresh</button>
  <div id="msg" class="muted" style="margin-top:10px;"></div>
  <div id="err" class="error"></div>
</div>

<div class="card">
  <h3 style="margin:0 0 10px 0;">Assigned devices</h3>
  <div id="listMsg" class="muted"></div>
  <table id="tbl" style="display:none;">
    <thead><tr><th>Device ID</th><th>Label</th><th>Action</th></tr></thead>
    <tbody></tbody>
  </table>
</div>


<script>
var USER_ID = parseInt($("#uid").text(), 10) || 0; // get the user id from inside of html codes 

function loadDropdown(){
  $("#msg").text("Loading devices...");
  $("#err").text("");
  var $sel = $("#sel").empty().prop("disabled", true);

  $.getJSON("api.php?action=devices", function(d){
    var list = d.devices || [];
    if(list.length === 0){
      $sel.append($("<option/>").val("").text("No devices"));
    } else {
      list.forEach(function(x){
        $sel.append(
          $("<option/>").val(x.device_id).attr("data-label", x.device_label || "")
          .text((x.device_label || "(no label)") + " — " + x.device_id)
        );
      });
    }
    $sel.prop("disabled", false); // active dropdown menu
    $("#msg").text("OK");
  }).fail(function(xhr){
    if (xhr.status === 401) window.location = "login.php";
    else $("#err").text(xhr.responseText || xhr.statusText);
  });
}

function loadUserDevices(){
  $("#listMsg").text("Loading...");
  $("#err").text("");
  $("#tbl").hide();

  $.getJSON("api.php?action=user_devices&user_id=" + USER_ID, function(d){
    var list = d.devices || [];
    $("#listMsg").text("User has " + list.length + " devices.");

    var $tb = $("#tbl tbody").empty();
    list.forEach(function(x){
      var tr = $("<tr/>");
      tr.append($("<td/>").text(x.device_id || ""));
      tr.append($("<td/>").text(x.device_label || ""));
      tr.append($("<td/>").append($("<button/>").text("Remove").attr("data-id", x.device_id || "")));
      $tb.append(tr);
    });
    $("#tbl").show();
  }).fail(function(xhr){
    if (xhr.status === 401) window.location = "login.php";
    else $("#err").text(xhr.responseText || xhr.statusText);
  });
}

function assignSelected(){
  var $opt = $("#sel option:selected");
  var device_id = $opt.val();
  var device_label = $opt.attr("data-label") || "";
  if(!device_id) return;

  $("#msg").text("Assigning...");
  $.ajax({
    url: "api.php?action=assign&user_id=" + USER_ID,
    method: "POST",
    contentType: "application/json",
    dataType: "json",
    data: JSON.stringify({ device_id: device_id, device_label: device_label }),
    success: function(){
      $("#msg").text("OK");
      loadUserDevices();
    },
    error: function(xhr){
      if (xhr.status === 401) window.location = "login.php";
      else $("#err").text(xhr.responseText || xhr.statusText);
    }
  });
}

function unassign(device_id){
  $("#msg").text("Removing...");
  $.ajax({
    url: "api.php?action=unassign&user_id=" + USER_ID,
    method: "POST",
    contentType: "application/json",
    dataType: "json",
    data: JSON.stringify({ device_id: device_id }),  //convert js obj to json string
    success: function(){
      $("#msg").text("OK");
      loadUserDevices();
    },
    error: function(xhr){
      if (xhr.status === 401) window.location = "login.php";
      else $("#err").text(xhr.responseText || xhr.statusText);
    }
  });
}

$("#btnAssign").on("click", assignSelected);
$("#btnRefresh").on("click", function(){ loadDropdown(); loadUserDevices(); });
$("#tbl").on("click", "button[data-id]", function(){ unassign($(this).attr("data-id")); });

loadDropdown();
loadUserDevices();
</script>

</body>
</html>
