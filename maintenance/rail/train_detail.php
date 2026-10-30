<?php
@ini_set('memory_limit','96M');
@set_time_limit(8);
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/rail_train_detail.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
require_once $private.'/lib/rail_train_detail.php';
try{
    $body=openroad_require_post_json();$db=openroad_db();openroad_require_signed($db,$body);
    $v=json_decode($body,true);
    if(!is_array($v))openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
    $id=filter_var($v['tripId']??null,FILTER_VALIDATE_INT);
    $dep=filter_var($v['departureEpoch']??null,FILTER_VALIDATE_INT);
    $from=strtoupper((string)($v['fromCrs']??''));
    $to=strtoupper((string)($v['toCrs']??''));
    if($id===false||$dep===false)openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
    $result=or_train_detail($private.'/cache/rail-routing/current',(int)$id,$from,$to,(int)$dep);
    openroad_json($result,200);
}catch(InvalidArgumentException $e){
    openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
}catch(Throwable $e){
    openroad_json(['ok'=>false,'error'=>'Train timetable is temporarily unavailable'],503);
}
