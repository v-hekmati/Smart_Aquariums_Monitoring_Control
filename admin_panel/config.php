<?php
// config.php
// Admin panel config

$config = [
  'service_catalogue' => 'http://localhost:8080', // GET /services and GET /devices
  'timeout'           => 7,                        // seconds

  'admin_username'    => 'admin',
  'admin_password'    => 'admin123',
];


return $config;
