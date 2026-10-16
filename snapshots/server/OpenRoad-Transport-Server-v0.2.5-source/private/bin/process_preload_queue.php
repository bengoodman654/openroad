<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
try{
  $db=openroad_db();openroad_schema($db);
  $q=$db->query('SELECT region_key FROM or_prepare_queue ORDER BY last_requested_at ASC LIMIT 1');
  $region=$q?$q->fetchColumn():false;
  if($region===false){echo "No queued OpenRoad region preparation.\n";exit(0);}
  $region=(string)$region;
  $script=__DIR__.'/update_gtfs.php';
  $cmd=escapeshellarg(PHP_BINARY).' -d memory_limit=768M '.escapeshellarg($script).' '.escapeshellarg($region);
  passthru($cmd,$code);
  if($code!==0){$e=$db->prepare('UPDATE or_prepare_queue SET attempts=attempts+1,last_error=?,last_requested_at=NOW() WHERE region_key=?');$e->execute(['Regional GTFS preparation failed with exit code '.$code,$region]);exit($code);}  
}catch(Throwable $e){fwrite(STDERR,'OpenRoad preload queue failed: '.$e->getMessage()."\n");exit(1);} 
