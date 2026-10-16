<?php
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
try{
  $body=openroad_require_post_json();$db=openroad_db();openroad_require_signed($db,$body);$data=json_decode($body,true);if(!is_array($data))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
  $lat=(float)($data['lat']??NAN);$lon=(float)($data['lon']??NAN);$reason=preg_replace('/[^a-z0-9_-]/i','',(string)($data['reason']??'destination'));
  if(!is_finite($lat)||!is_finite($lon)||abs($lat)>90||abs($lon)>180)openroad_json(['ok'=>false,'error'=>'Invalid location'],400);
  $region=openroad_region_for_point($lat,$lon);if($region===null)openroad_json(['ok'=>true,'state'=>'unsupported','region'=>'','message'=>'No regional BODS preparation is configured for this area.']);
  $r=openroad_enqueue_region($db,$region,$reason?:'destination');$r['ok']=true;openroad_json($r);
}catch(Throwable $e){openroad_log_error($e);openroad_json(['ok'=>false,'error'=>'Service unavailable'],503);} 
