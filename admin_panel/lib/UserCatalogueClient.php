<?php

class UserCatalogueClient
{
  
  private $http;


  private $discovery;


  private $userCatalogueUrl;


  public function __construct($http, $discovery)
  {
    $this->http = $http;
    $this->discovery = $discovery;

    
    $this->userCatalogueUrl = $this->discovery->urlOf('user_catalogue');
  }


  public function base()
  {
    return $this->userCatalogueUrl;
  }

  
  public function listUsers()
  {
    return $this->http->request('GET', $this->userCatalogueUrl . '/users');
  }

 
  public function createUser($username, $password)
  {
    return $this->http->request('POST', $this->userCatalogueUrl . '/users', [
      'username' => (string)$username,
      'password' => (string)$password,
    ]);
  }

  
  public function listUserDevices($userId)
  {
    $userId = (int)$userId;
    return $this->http->request('GET', $this->userCatalogueUrl . '/user_devices?user_id=' . $userId);
  }

  
  public function assignDevice($userId, $deviceId, $deviceLabel = '')
  {
    return $this->http->request('POST', $this->userCatalogueUrl . '/assign', [
      'user_id'      => (int)$userId,
      'device_id'    => (string)$deviceId,
      'device_label' => (string)$deviceLabel,
    ]);
  }

  public function unassignDevice($userId, $deviceId)
  {
    return $this->http->request('POST', $this->userCatalogueUrl . '/unassign', [
      'user_id'   => (int)$userId,
      'device_id' => (string)$deviceId,
    ]);
  }
}
