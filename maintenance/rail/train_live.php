<?php
@ini_set('memory_limit','64M');@set_time_limit(9);
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/rail_train_live.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
require_once $private.'/lib/rail_train_live.php';
try{
    $body=openroad_require_post_json();
    $db=openroad_db();openroad_require_signed($db,$body);
    $input=json_decode($body,true);
    if(!is_array($input))openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
    $from=strtoupper((string)($input['fromCrs']??''));
    $to=strtoupper((string)($input['toCrs']??''));
    $dep=filter_var($input['departureEpoch']??null,FILTER_VALIDATE_INT);
    if($dep===false)openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
    $headsign=substr((string)($input['headsign']??''),0,80);
    $result=or_train_live_lookup($from,$to,(int)$dep,$headsign);
    openroad_json(['ok'=>true]+$result,200);
}catch(InvalidArgumentException $e){
    openroad_json(['ok'=>false,'error'=>'Invalid train selection'],400);
}catch(Throwable $e){
    openroad_json(['ok'=>false,'error'=>'Live train data is unavailable'],503);
}
