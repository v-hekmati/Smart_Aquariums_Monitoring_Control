<?php
require __DIR__ . '/auth.php';

$auth = new Auth($config);

if ($auth->isLoggedIn()) {
  header('Location: index.php');
  exit;
}

$err = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
  $username = trim($_POST['username']);
  $password = trim($_POST['password']);
  if ($auth->login($username, $password)) {
    header('Location: index.php');
    exit;
  } else {
    $err = 'Invalid username or password';
  }
}
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login</title>
<style>
  :root{
    --bg:#f6f7fb;
    --card:#ffffff;
    --border:#e7e7ef;
    --muted:#6b7280;
    --danger:#b00020;
  }

  *{box-sizing:border-box;}
  body{
    font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;
    margin:24px;
    background:var(--bg);
    min-height:90vh;
    display:flex;
    justify-content:center;
    align-items:center;
  }

  /* Split layout container */
  .panel{
    width:min(980px, 100%);
    background:var(--card);
    border:1px solid var(--border);
    border-radius:16px;
    overflow:hidden;
    display:flex;
    box-shadow:0 10px 30px rgba(0,0,0,.06);
  }

  /* Left: login */
  .login{
    flex: 1 1 460px;
    padding:44px;
    display:flex;
    align-items:center;
    justify-content:center;
  }
  .login-inner{width:min(420px, 100%); text-align:center;}

  h2{margin:0 0 8px 0; font-size:28px;}
  .muted{color:var(--muted); font-size:13px; margin-bottom:18px;}

  input{
    width:100%;
    padding:11px 12px;
    border:1px solid #ddd;
    border-radius:6px;
    margin:7px 0;
    outline:none;
    background:#fff;
  }
  input:focus{border-color:#bfc6d6; box-shadow:0 0 0 4px rgba(148,163,184,.25);}

  button{
    width:100%;
    padding:11px 12px;
    border:1px solid #ddd;
    border-radius:6px;
    background:#f2f2f7;
    cursor:pointer;
    margin-top:12px;
    font-weight:600;
  }
  button:hover{filter:brightness(.98);}

  .error{color:var(--danger); margin-top:12px; font-size:13px;}

  /* Right: image */
  .hero{
    flex: 1 1 520px;
    min-height:420px;
    position:relative;
    background:#0b2a3a;
  }
  .hero img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
  }

 
</style>
</head>
<body>
  <div class="panel">

    <div class="login">
      <div class="login-inner">
        <h3> Smart Aquariums - Admin pannel</h3>
        <div class="muted">Login</div>

        <form method="post">
          <input name="username" placeholder="username" autocomplete="username" required>
          <input name="password" type="password" placeholder="password" autocomplete="current-password" required>
          <button type="submit">Login</button>

          <?php if ($err): ?>
            <div class="error"><?= htmlspecialchars($err) ?></div>
          <?php endif; ?>
        </form>
      </div>
    </div>

    <div class="hero" aria-hidden="true">
     
      <img src="assets/login-side.jpg" alt="">
    </div>

  </div>
</body>
</html>
