<?php
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')){http_response_code(404);exit;}
require_once $private.'/lib/auth.php';
try{
    $body=openroad_require_post_json();$db=openroad_db();openroad_schema($db);$auth=openroad_require_signed($db,$body);
    openroad_json(['ok'=>true,'version'=>'0.2.4','paired'=>true,'deviceId'=>$auth['deviceId'],'datasetReady'=>openroad_current_dataset($db)>0,'datasetUpdated'=>openroad_meta($db,'updated_at','never'),'region'=>openroad_config()['region']??'','regions'=>openroad_region_status($db)]);
}catch(Throwable $e){openroad_log_error($e);openroad_json(['ok'=>false,'error'=>'Service unavailable'],503);}
