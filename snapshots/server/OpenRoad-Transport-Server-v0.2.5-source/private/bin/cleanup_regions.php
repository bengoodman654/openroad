<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
try{
  $db=openroad_db();openroad_schema($db);$ttl=max(7,(int)(openroad_config()['prepared_region_ttl_days']??60));
  $q=$db->prepare('SELECT region_key,dataset_id FROM or_regions WHERE permanent=0 AND last_used_at < DATE_SUB(NOW(), INTERVAL ? DAY)');$q->execute([$ttl]);$rows=$q->fetchAll();
  foreach($rows as $r){$ds=(int)$r['dataset_id'];foreach(['or_stops','or_routes','or_trips','or_stop_times','or_service_dates','or_shapes'] as $table){$d=$db->prepare("DELETE FROM $table WHERE dataset_id=?");$d->execute([$ds]);}$db->prepare('DELETE FROM or_regions WHERE region_key=?')->execute([$r['region_key']]);$db->prepare('DELETE FROM or_journey_cache WHERE region_key=?')->execute([$r['region_key']]);$db->prepare('DELETE FROM or_service_cache WHERE region_key=?')->execute([$r['region_key']]);echo 'Expired '. $r['region_key']."\n";}
  $db->exec('DELETE FROM or_journey_cache WHERE expires_at<NOW()');$db->exec('DELETE FROM or_service_cache WHERE expires_at<NOW()');
}catch(Throwable $e){fwrite(STDERR,'OpenRoad cleanup failed: '.$e->getMessage()."\n");exit(1);} 
