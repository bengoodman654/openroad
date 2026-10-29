<?php
// Isolated read-only rail gateway. Does not alter bus routing, timetable jobs or schemas.
@ini_set('memory_limit','64M');
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/rail_gateway.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
require_once $private.'/lib/rail_gateway.php';
try {
    $body=openroad_require_post_json();
    $db=openroad_db();
    openroad_require_signed($db,$body);
    $request=json_decode($body,true);
    if(!is_array($request))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    [$status,$result]=openroad_rail_board((string)($request['station']??''));
    if($status===429 || $status===503)header('Retry-After: 60');
    openroad_json($result,$status);
} catch(Throwable $e){
    // Avoid logging upstream payloads, headers, credentials or personal journey searches.
    openroad_json(['ok'=>false,'error'=>'Rail departure service is unavailable'],503);
}
