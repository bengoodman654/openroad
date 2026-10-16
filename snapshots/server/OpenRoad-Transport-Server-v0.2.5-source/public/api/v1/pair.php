<?php
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
try{
    $body=openroad_require_post_json();$data=json_decode($body,true);if(!is_array($data))openroad_json(['ok'=>false,'error'=>'Pairing failed'],400);
    $db=openroad_db();openroad_schema($db);$paired=openroad_pair_device($db,$data);
    openroad_json(['ok'=>true,'paired'=>true,'deviceId'=>$paired['deviceId']],201);
}catch(Throwable $e){openroad_log_error($e);openroad_json(['ok'=>false,'error'=>'Pairing failed'],500);}
