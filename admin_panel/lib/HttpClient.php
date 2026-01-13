<?php

class HttpClient
{
  private $timeout;

  
  public function __construct($timeoutSeconds)
  {
    $this->timeout = (int)$timeoutSeconds;
  }

  public function request($method, $url, $data = null)
  {
    $method = strtoupper((string)$method);

    $opts = [
      'http' => [
        'method'  => $method,
        'timeout' => $this->timeout,
        'header'  => "Accept: application/json\r\n",
      ],
    ];

    if ($data !== null) {
      $opts['http']['header']  .= "Content-Type: application/json\r\n";
      $opts['http']['content']  = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    $ctx  = stream_context_create($opts); // set the request configuration
    $raw  = file_get_contents($url, false, $ctx); //execute the request and get raw response
    $json = json_decode($raw, true); //decode JSON response into associative array

    
    return $json;
  }
}
