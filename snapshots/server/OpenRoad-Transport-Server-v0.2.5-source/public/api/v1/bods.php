<?php
/** BODS on-demand gateway; signed phone requests only. No background work. */
@ini_set('memory_limit','64M');
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/bods_gateway.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
require_once $private.'/lib/bods_gateway.php';
try {
    $body=openroad_require_post_json();
    $db=openroad_db();
    openroad_require_signed($db,$body);
    $request=json_decode($body,true);
    if(!is_array($request))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    [$status,$result]=openroad_bods_live((string)($request['line']??''),
        (float)($request['lat']??NAN),(float)($request['lon']??NAN));
    if($status===429||$status===503)header('Retry-After: 60');
    openroad_json($result,$status);
}catch(Throwable $e){
    // Do not log credentials, full URLs, upstream replies or precise location.
    openroad_json(['ok'=>false,'error'=>'Live bus service is unavailable'],503);
}
