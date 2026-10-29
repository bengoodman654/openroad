<?php
// Signed, read-only private railway planner. Never accepts filenames or provider URLs.
@ini_set('memory_limit','96M');
@set_time_limit(9);
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/rail_planner.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
require_once $private.'/lib/rail_planner.php';
try {
    $body=openroad_require_post_json();
    $db=openroad_db();
    openroad_require_signed($db,$body);
    $request=json_decode($body,true);
    if(!is_array($request))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    $from=$request['from']??null;$to=$request['to']??null;
    if(!is_array($from)||!is_array($to))openroad_json(['ok'=>false,'error'=>'Invalid location'],400);
    foreach([$from,$to] as $p){
        if(!isset($p['lat'],$p['lon'])||!is_numeric($p['lat'])||!is_numeric($p['lon'])||
           !is_finite((float)$p['lat'])||!is_finite((float)$p['lon'])||
           abs((float)$p['lat'])>90||abs((float)$p['lon'])>180)
            openroad_json(['ok'=>false,'error'=>'Invalid location'],400);
    }
    $plan=or_rail_plan((float)$from['lat'],(float)$from['lon'],(float)$to['lat'],(float)$to['lon']);
    if(!$plan['routes'])openroad_json(['ok'=>false,'error'=>'No scheduled rail journey found within walking distance'],422);
    openroad_json($plan+['ok'=>true],200);
} catch(RuntimeException $e) {
    openroad_json(['ok'=>false,'error'=>'Rail timetable unavailable or out of date'],503);
} catch(Throwable $e) {
    openroad_json(['ok'=>false,'error'=>'Rail journey planning unavailable'],503);
}
