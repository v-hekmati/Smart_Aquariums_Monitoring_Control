<?php


class ServiceDiscovery
{
 
  private $http;


  private $serviceCatalogueBaseUrl;

 
  public function __construct($http, $serviceCatalogueBaseUrl)
  {
    $this->http = $http;
    $this->serviceCatalogueBaseUrl = rtrim((string)$serviceCatalogueBaseUrl, '/');
  }

  
  public function urlOf($serviceName)
  {
    $services = $this->http->request('GET', $this->serviceCatalogueBaseUrl . '/services');
    $list = isset($services['services']) ? $services['services'] : [];

    foreach ($list as $svc) {
      $name = isset($svc['name']) ? (string)$svc['name'] : '';
      $url  = isset($svc['url']) ? (string)$svc['url'] : '';
      if ($name === (string)$serviceName && $url !== '') {
        return rtrim($url, '/');
      }
    }

    return '';
  }
}
