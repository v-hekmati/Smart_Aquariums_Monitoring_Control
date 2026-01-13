<?php
require __DIR__ . '/auth.php';
$auth = new Auth($config);
$auth->requireLogin();
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin - Users</title>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<style>
  body{font-family:system-ui; margin:24px; background:#f6f7fb;}
  .card{background:#fff; border:1px solid #e7e7ef; border-radius:14px; padding:16px; margin-bottom:16px;}
  input{padding:10px 12px; border:1px solid #ddd; border-radius:10px; min-width:220px;}
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
      <h2 style="margin:0 0 6px 0;">Admin - Users</h2>
      <div class="muted">Logged in as: <b><?= htmlspecialchars($_SESSION['admin_username'] ?? 'admin') ?></b></div>
    </div>
    <div><a href="logout.php">Logout</a></div>
  </div>
</div>

<div class="card">
  <h3 style="margin:0 0 10px 0;">Create user</h3>
  <input id="username" placeholder="username">
  <input id="password" placeholder="password">
  <button id="btnCreate">Create</button>
  <button id="btnRefresh">Refresh</button>
  <div id="msg" class="muted" style="margin-top:10px;"></div>
  <div id="err" class="error"></div>
</div>

<div class="card">
  <h3 style="margin:0 0 10px 0;">Users</h3>
  <div id="usersMsg" class="muted"></div>
  <table id="tbl" style="display:none;">
    <thead><tr><th>ID</th><th>Username</th><th>Chat ID</th><th>Manage</th></tr></thead>
    <tbody></tbody>
  </table>
</div>


<script>
function loadUsers(){
  $("#usersMsg").text("Loading...");
  $("#err").text("");
  $("#tbl").hide();

  $.getJSON("api.php?action=users_list", function(d){
    var list = d.users || [];
    $("#usersMsg").text("Found " + list.length + " users.");

    var $tb = $("#tbl tbody").empty();
    list.forEach(function(u){
      var uid = u.user_id;
      var tr = $("<tr/>");
      tr.append($("<td/>").text(uid));
      tr.append($("<td/>").text(u.username || ""));
      tr.append($("<td/>").text(u.telegram_chat_id || ""));
      tr.append($("<td/>").append($("<a/>").attr("href","user_devices.php?user_id="+uid).text("Assign devices")));
      $tb.append(tr);
    });

    $("#tbl").show();
  }).fail(function(xhr){
    if (xhr.status === 401) window.location = "login.php";
    else $("#err").text(xhr.responseText || xhr.statusText);
  });
}

function createUser(){
  $("#msg").text("Creating...");
  $("#err").text("");

  $.ajax({
    url: "api.php?action=users_create",
    method: "POST",
    contentType: "application/json",
    dataType: "json",
    data: JSON.stringify({
      username: $("#username").val(),
      password: $("#password").val()
    }),
    success: function(){
      $("#msg").text("OK . user created ");
      $("#username").val(""); $("#password").val("");
      loadUsers();
    },
    error: function(xhr){
      if (xhr.status === 401) window.location = "login.php";
      else $("#err").text(xhr.responseText || xhr.statusText);
    }
  });
}

$("#btnCreate").on("click", createUser);
$("#btnRefresh").on("click", loadUsers);


loadUsers();


</script>

</body>
</html>
