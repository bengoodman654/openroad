<?php
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/router.php')){http_response_code(404);exit;}
require_once $private.'/lib/router.php';
require_once $private.'/lib/auth.php';
$started=microtime(true);
$phase='full';
$stage='authentication';
try{
    $body=openroad_require_post_json();$db=openroad_db();openroad_require_signed($db,$body);
    $data=json_decode($body,true);if(!is_array($data))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    $from=$data['from']??null;$to=$data['to']??null;$settings=is_array($data['settings']??null)?$data['settings']:[];
    $fromLat=(float)($from['lat']??NAN);$fromLon=(float)($from['lon']??NAN);$toLat=(float)($to['lat']??NAN);$toLon=(float)($to['lon']??NAN);
    if(!is_finite($fromLat)||!is_finite($fromLon)||!is_finite($toLat)||!is_finite($toLon))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    if(abs($fromLat)>90||abs($toLat)>90||abs($fromLon)>180||abs($toLon)>180)openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    $safe=['maxWalk'=>max(3,min(60,(int)($settings['maxWalk']??10))),'walkSpeed'=>in_array(($settings['walkSpeed']??'normal'),['slow','normal','fast'],true)?$settings['walkSpeed']:'normal','transferBuffer'=>($settings['transferBuffer']??'normal')==='cautious'?'cautious':'normal','ranking'=>in_array(($settings['ranking']??'balanced'),['quickest','balanced','changes'],true)?$settings['ranking']:'balanced','resultLimit'=>max(3,min(9,(int)($settings['resultLimit']??3))),'phase'=>(($settings['phase']??'full')==='fast'?'fast':'full')];
    $phase=$safe['phase'];
    $stage='route';
    // Both MySQL 8 and MariaDB have session-scoped SELECT timeouts, but different names.
    // An unsupported variable is ignored; it must not make an otherwise working server fail.
    $queryLimit=$phase==='fast'?3000:4500;
    try { $db->exec('SET SESSION max_statement_time = '.($queryLimit/1000)); }
    catch(Throwable $ignored) {
        try { $db->exec('SET SESSION max_execution_time = '.$queryLimit); }
        catch(Throwable $ignoredAgain) {}
    }
    $result=openroad_plan_bus($db,$fromLat,$fromLon,$toLat,$toLon,$safe);
    $result['ok']=true;
    openroad_route_perf_log($phase,'ok',$result['clearRouteCache']??'miss',$started,count($result['routes']??[]));
    openroad_json($result);
}catch(RuntimeException $e){
    openroad_route_perf_log($phase,'not_found','none',$started,0);
    openroad_json(['ok'=>false,'error'=>$e->getMessage()],422);
}catch(Throwable $e){
    openroad_route_perf_log($phase,'error','none',$started,0);
    openroad_log_error($e);
    openroad_json(['ok'=>false,'error'=>'Service unavailable'],503);
}
