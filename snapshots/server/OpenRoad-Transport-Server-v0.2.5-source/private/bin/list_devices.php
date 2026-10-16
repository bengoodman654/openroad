<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
try{$db=openroad_db();openroad_schema($db);$q=$db->query('SELECT device_id,device_label,created_at,last_seen_at,revoked_at FROM or_devices ORDER BY created_at');foreach($q as $r)echo implode(' | ',[$r['device_id'],$r['device_label'],$r['revoked_at']?'REVOKED':'ACTIVE',$r['created_at'],$r['last_seen_at']??'never']).PHP_EOL;}
catch(Throwable $e){fwrite(STDERR,$e->getMessage().PHP_EOL);exit(1);}
