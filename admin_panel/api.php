<?php
//   AJAX backend 
// - Requires login
// - Discovers user_catalogue from Service Catalogue (GET /services)
// - Devices always from Service/resourse Catalogue (GET /devices)

require __DIR__ . '/auth.php';
$auth = new Auth($config);
// check login 
 if (!$auth->isLoggedIn()) {
    send_json(['ok' => false, 'error' => 'unauthorized']);
}
// Tell the client that the response is JSON
header('Content-Type: application/json; charset=utf-8');

global $config;

require __DIR__ . '/lib/HttpClient.php';
require __DIR__ . '/lib/ServiceDiscovery.php';
require __DIR__ . '/lib/UserCatalogueClient.php';

 

// Read JSON body of HTTP request and return as array (or empty array)
function read_json() {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);

    if (is_array($data)) {
        return $data;
    }
    return [];
}

// Send JSON response and stop
function send_json($arr) {
    echo json_encode($arr);
    exit;
}



$timeout = 7;
if (isset($config['timeout'])) {
    $timeout = (int)$config['timeout'];
}

$serviceCatalogue = '';
if (isset($config['service_catalogue'])) {
    $serviceCatalogue = $config['service_catalogue']; // get the address of service catalogue 
}

// ---------- load the libraries   ----------

$http = new HttpClient($timeout); // for sending request 
$disc = new ServiceDiscovery($http, $serviceCatalogue); // for service discovery from service catalogue 
$user = new UserCatalogueClient($http, $disc); // fo working with UserCatalogue

// ---------- action ----------

$action = '';
if (isset($_GET['action'])) {
    $action = $_GET['action'];
}

// Handle API requests and return JSON responses based on the action parameter
switch ($action) {

    case 'devices': //  Return the list of devices from Service Catalogue
        $base = rtrim($serviceCatalogue, '/');
        $data = $http->request('GET', $base . '/devices');

        
        $list =  $data['devices']; //API returns {"devices":[{},{}]}

        $out = []; 
        foreach ($list as $d) {
            $out[] = [
                'device_id'    => $d['device_id'],
                'device_label' => isset($d['device_label']) ? $d['device_label'] : '',
            ];
        }

        send_json(['ok' => true, 'devices' => $out]);
        break;

    case 'users_list': // Return the list of users from User Catalogue
        $data = $user->listUsers(); // get the list of all users fron user catalouge 
        $users =  $data['users'];
        send_json(['ok' => true, 'users' => $users]);
        break;

    case 'users_create':
        $j = read_json();
        $username = isset($j['username']) ? $j['username'] : '';
        $password = isset($j['password']) ? $j['password'] : '';

        $data = $user->createUser($username, $password);
        send_json(['ok' => true, 'data' => $data]);
        break;

    case 'user_devices': // Get all devices assigned to a specific user
        $user_id = isset($_GET['user_id']) ? (int)$_GET['user_id'] : 0;

        $data = $user->listUserDevices($user_id);
        $devices = isset($data['devices']) ? $data['devices'] : [];
        send_json(['ok' => true, 'devices' => $devices]);
        break;

    case 'assign':   // Assign a device to a user
        $user_id = isset($_GET['user_id']) ? (int)$_GET['user_id'] : 0;
        $j = read_json();

        $device_id = isset($j['device_id']) ? $j['device_id'] : '';
        $device_label = isset($j['device_label']) ? $j['device_label'] : '';

        $data = $user->assignDevice($user_id, $device_id, $device_label);
        send_json(['ok' => true, 'data' => $data]);
        break;

    case 'unassign':  // Remove a device from a user
        $user_id = isset($_GET['user_id']) ? (int)$_GET['user_id'] : 0;
        $j = read_json();

        $device_id = isset($j['device_id']) ? $j['device_id'] : '';

        $data = $user->unassignDevice($user_id, $device_id);
        send_json(['ok' => true, 'data' => $data]);
        break;

    default:
        send_json(['ok' => false, 'error' => 'unknown action']);
}
