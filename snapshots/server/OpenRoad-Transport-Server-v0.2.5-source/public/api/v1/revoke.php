<?php
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
try{
    $body=openroad_require_post_json();$db=openroad_db();openroad_schema($db);$auth=openroad_require_signed($db,$body);
    $q=$db->prepare('UPDATE or_devices SET revoked_at=NOW() WHERE device_id=?');$q->execute([$auth['deviceId']]);
    openroad_json(['ok'=>true,'revoked'=>true]);
}catch(Throwable $e){openroad_log_error($e);openroad_json(['ok'=>false,'error'=>'Service unavailable'],503);}
