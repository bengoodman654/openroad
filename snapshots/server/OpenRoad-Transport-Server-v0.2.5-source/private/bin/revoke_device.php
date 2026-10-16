<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
$id=$argv[1]??'';if(!preg_match('/^[0-9a-fA-F-]{36}$/',$id)){fwrite(STDERR,"Usage: php revoke_device.php DEVICE_ID\n");exit(2);}try{$db=openroad_db();openroad_schema($db);$q=$db->prepare('UPDATE or_devices SET revoked_at=NOW() WHERE device_id=?');$q->execute([$id]);echo $q->rowCount()?"Device revoked.\n":"Device not found or already revoked.\n";}
catch(Throwable $e){fwrite(STDERR,$e->getMessage().PHP_EOL);exit(1);}
