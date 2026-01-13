<?php
require __DIR__ . '/config.php';

class Auth
{
    private array $cfg;

    public function __construct(array $cfg)
    {
        $this->cfg = $cfg;
        if (session_status() === PHP_SESSION_NONE) {
            session_start();
        }
    }

    public function isLoggedIn(): bool
    {
        return !empty($_SESSION['admin_logged_in']); // check if  the session for login exist or not  
    }

    public function requireLogin(): void // if you are not logged in redirected to login.php
    {
        if (!$this->isLoggedIn()) {
            header('Location: login.php');
            exit;
        }
    }

    public function login(string $username, string $password): bool
    {
        $adminUser = $this->cfg['admin_username'];
        $adminPass = $this->cfg['admin_password'];

        if ($username === $adminUser && $password === $adminPass) {
            $_SESSION['admin_logged_in'] = true;
            $_SESSION['admin_username'] = $username;
            return true;
        }
        return false;
    }

    public function logout(): void
    {
        session_destroy();
    }
}


