<?php
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require_once dirname(__DIR__) . '/lib/bootstrap.php';

function logline(string $s): void { echo '['.date('Y-m-d H:i:s').'] '.$s.PHP_EOL; }
function require_ext(string $ext): void { if(!extension_loaded($ext)) throw new RuntimeException("PHP extension '$ext' is required."); }
function gtfs_sec(string $v): ?int { $p=explode(':',trim($v)); if(count($p)<2)return null; return ((int)$p[0])*3600+((int)$p[1])*60+(int)($p[2]??0); }
function clean_header(array $h): array { return array_map(fn($v)=>strtolower(trim(preg_replace('/^\xEF\xBB\xBF/','',(string)$v))),$h); }
function zip_rows(ZipArchive $zip,string $name,callable $fn): void {
    $idx=$zip->locateName($name,ZipArchive::FL_NOCASE); if($idx===false)return;
    $stream=$zip->getStream($zip->getNameIndex($idx)); if(!$stream)throw new RuntimeException("Could not open $name");
    $header=fgetcsv($stream); if(!$header){fclose($stream);return;} $header=clean_header($header);$map=array_flip($header);
    while(($row=fgetcsv($stream))!==false){$get=function(string $k,string $d='')use($row,$map){$i=$map[$k]??null;return $i===null?$d:trim((string)($row[$i]??$d));};$fn($get,$row,$map);} fclose($stream);
}
function batch_insert(PDO $db,string $table,array $cols,array &$rows,int $batchSize=400): void {
    if(!$rows)return;
    foreach(array_chunk($rows,$batchSize) as $chunk){
        $values=[];$params=[];$one='('.implode(',',array_fill(0,count($cols),'?')).')';
        foreach($chunk as $r){$values[]=$one;foreach($r as $v)$params[]=$v;}
        $sql='INSERT INTO '.$table.' ('.implode(',',$cols).') VALUES '.implode(',',$values);
        $q=$db->prepare($sql);$q->execute($params);
    }
    $rows=[];
}
function download_file(string $url,string $dest): void {
    $tmp=$dest.'.part';@unlink($tmp);$out=fopen($tmp,'wb');if(!$out)throw new RuntimeException('Could not create GTFS download file.');
    if(function_exists('curl_init')){
        $ch=curl_init($url);curl_setopt_array($ch,[CURLOPT_FILE=>$out,CURLOPT_FOLLOWLOCATION=>true,CURLOPT_CONNECTTIMEOUT=>20,CURLOPT_TIMEOUT=>600,CURLOPT_USERAGENT=>'OpenRoad-Transport-Server/0.2.2',CURLOPT_FAILONERROR=>true]);
        $ok=curl_exec($ch);$err=curl_error($ch);$code=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE);curl_close($ch);fclose($out);if(!$ok)throw new RuntimeException("GTFS download failed (HTTP $code): $err");
    }else{
        $ctx=stream_context_create(['http'=>['follow_location'=>1,'timeout'=>600,'header'=>"User-Agent: OpenRoad-Transport-Server/0.2.2\r\n"]]);$in=fopen($url,'rb',false,$ctx);if(!$in){fclose($out);throw new RuntimeException('Could not download GTFS feed.');}stream_copy_to_stream($in,$out);fclose($in);fclose($out);
    }
    if(!is_file($tmp)||filesize($tmp)<10000){@unlink($tmp);throw new RuntimeException('Downloaded GTFS file is unexpectedly small.');}
    if(is_file($dest))@unlink($dest);if(!rename($tmp,$dest))throw new RuntimeException('Could not move downloaded GTFS file into place.');
}
function ymd_to_date(string $s): ?DateTimeImmutable { if(strlen($s)!==8)return null;$d=DateTimeImmutable::createFromFormat('!Ymd',$s);return $d?:null; }

try{
    require_ext('pdo_mysql');require_ext('zip');$cfg=openroad_config();$root=dirname(__DIR__);$cache=$root.'/cache';if(!is_dir($cache)&&!mkdir($cache,0750,true))throw new RuntimeException('Could not create cache directory.');
    $region=$argv[1]??($cfg['region']??'south_west');$regionCfg=openroad_region_config((string)$region);if(!is_array($regionCfg))throw new RuntimeException('Unknown OpenRoad region: '.$region);
    $lock=fopen($cache.'/update.lock','c+');if(!$lock||!flock($lock,LOCK_EX|LOCK_NB))throw new RuntimeException('Another GTFS update is already running.');
    $db=openroad_db();openroad_schema($db);$oldDs=openroad_region_dataset($db,$region);$zipPath=$cache.'/'.$region.'_gtfs.zip';$regionLabel=(string)($regionCfg['label']??$region);$regionUrl=(string)($regionCfg['url']??'');if($regionUrl==='')throw new RuntimeException('No GTFS URL is configured for '.$region);logline('Downloading official DfT/BODS '.$regionLabel.' GTFS…');download_file($regionUrl,$zipPath);logline('Download complete: '.round(filesize($zipPath)/1048576,1).' MB');
    $zip=new ZipArchive();if($zip->open($zipPath)!==true)throw new RuntimeException('Downloaded file is not a readable ZIP archive.');$ds=(int)(time().substr((string)microtime(true),-3));

    logline('Importing stops…');$rows=[];$count=0;zip_rows($zip,'stops.txt',function($g)use(&$rows,&$count,$db,$ds){$id=$g('stop_id');$lat=$g('stop_lat');$lon=$g('stop_lon');if($id===''||$lat===''||$lon==='')return;$rows[]=[$ds,$id,$g('stop_name'),(float)$lat,(float)$lon];$count++;if(count($rows)>=600)batch_insert($db,'or_stops',['dataset_id','stop_id','stop_name','stop_lat','stop_lon'],$rows,600);});batch_insert($db,'or_stops',['dataset_id','stop_id','stop_name','stop_lat','stop_lon'],$rows,600);logline("Stops: $count");
    logline('Importing routes…');$rows=[];$count=0;zip_rows($zip,'routes.txt',function($g)use(&$rows,&$count,$db,$ds){$id=$g('route_id');if($id==='')return;$rows[]=[$ds,$id,$g('route_short_name'),$g('route_long_name'),$g('route_type')];$count++;if(count($rows)>=500)batch_insert($db,'or_routes',['dataset_id','route_id','short_name','long_name','route_type'],$rows,500);});batch_insert($db,'or_routes',['dataset_id','route_id','short_name','long_name','route_type'],$rows,500);logline("Routes: $count");
    logline('Importing trips…');$rows=[];$count=0;zip_rows($zip,'trips.txt',function($g)use(&$rows,&$count,$db,$ds){$id=$g('trip_id');if($id==='')return;$rows[]=[$ds,$id,$g('route_id'),$g('service_id'),$g('shape_id'),$g('trip_headsign'),$g('direction_id')];$count++;if(count($rows)>=500)batch_insert($db,'or_trips',['dataset_id','trip_id','route_id','service_id','shape_id','headsign','direction_id'],$rows,500);});batch_insert($db,'or_trips',['dataset_id','trip_id','route_id','service_id','shape_id','headsign','direction_id'],$rows,500);logline("Trips: $count");

    logline('Building active service dates…');$today=new DateTimeImmutable('today');$days=max(7,(int)($cfg['service_days_ahead']??45));$wanted=[];for($i=0;$i<=$days;$i++){$d=$today->modify("+$i day");$wanted[$d->format('Ymd')]=$d->format('Y-m-d');}$active=[];
    zip_rows($zip,'calendar.txt',function($g)use(&$active,$wanted){$sid=$g('service_id');$start=$g('start_date');$end=$g('end_date');if($sid===''||$start===''||$end==='')return;$weekday=['sun'=>'sunday','mon'=>'monday','tue'=>'tuesday','wed'=>'wednesday','thu'=>'thursday','fri'=>'friday','sat'=>'saturday'];foreach($wanted as $ymd=>$iso){if($ymd<$start||$ymd>$end)continue;$d=DateTimeImmutable::createFromFormat('!Ymd',$ymd);$key=$weekday[strtolower($d->format('D'))]??'';if($key!==''&&$g($key)==='1')$active[$ymd][$sid]=true;}});
    zip_rows($zip,'calendar_dates.txt',function($g)use(&$active,$wanted){$ymd=$g('date');$sid=$g('service_id');if(!isset($wanted[$ymd])||$sid==='')return;$type=$g('exception_type');if($type==='1')$active[$ymd][$sid]=true;elseif($type==='2')unset($active[$ymd][$sid]);});
    $rows=[];$count=0;foreach($active as $ymd=>$services){$iso=$wanted[$ymd];foreach(array_keys($services) as $sid){$rows[]=[$ds,$sid,$iso];$count++;if(count($rows)>=700)batch_insert($db,'or_service_dates',['dataset_id','service_id','service_date'],$rows,700);}}batch_insert($db,'or_service_dates',['dataset_id','service_id','service_date'],$rows,700);logline("Service-date rows: $count");

    logline('Importing stop times (largest step)…');$rows=[];$count=0;zip_rows($zip,'stop_times.txt',function($g)use(&$rows,&$count,$db,$ds){$trip=$g('trip_id');$stop=$g('stop_id');$seq=(int)$g('stop_sequence');$a=gtfs_sec($g('arrival_time'));$d=gtfs_sec($g('departure_time'));if($trip===''||$stop===''||($a===null&&$d===null))return;if($a===null)$a=$d;if($d===null)$d=$a;$rows[]=[$ds,$trip,$stop,$seq,$a,$d];$count++;if(count($rows)>=700)batch_insert($db,'or_stop_times',['dataset_id','trip_id','stop_id','stop_sequence','arrival_sec','departure_sec'],$rows,700);});batch_insert($db,'or_stop_times',['dataset_id','trip_id','stop_id','stop_sequence','arrival_sec','departure_sec'],$rows,700);logline("Stop-time rows: $count");

    $sample=1;logline('Importing full route shapes…');$rows=[];$count=0;zip_rows($zip,'shapes.txt',function($g)use(&$rows,&$count,$db,$ds,$sample){$seq=(int)$g('shape_pt_sequence');if($seq%$sample!==0&&$seq!==1)return;$sid=$g('shape_id');$lat=$g('shape_pt_lat');$lon=$g('shape_pt_lon');if($sid===''||$lat===''||$lon==='')return;$rows[]=[$ds,$sid,$seq,(float)$lat,(float)$lon];$count++;if(count($rows)>=700)batch_insert($db,'or_shapes',['dataset_id','shape_id','point_sequence','point_lat','point_lon'],$rows,700);});batch_insert($db,'or_shapes',['dataset_id','shape_id','point_sequence','point_lat','point_lon'],$rows,700);logline("Shape points: $count");$zip->close();

    $db->beginTransaction();
    $permanent=!empty($regionCfg['permanent'])?1:0;
    $rq=$db->prepare('INSERT INTO or_regions(region_key,dataset_id,label,updated_at,last_used_at,permanent) VALUES(?,?,?,NOW(),NOW(),?) ON DUPLICATE KEY UPDATE dataset_id=VALUES(dataset_id),label=VALUES(label),updated_at=NOW(),last_used_at=NOW(),permanent=VALUES(permanent)');$rq->execute([$region,$ds,$regionLabel,$permanent]);
    if($region==='south_west'){$set=$db->prepare('INSERT INTO or_meta(meta_key,meta_value) VALUES(?,?) ON DUPLICATE KEY UPDATE meta_value=VALUES(meta_value)');foreach(['current_dataset'=>(string)$ds,'updated_at'=>date(DATE_ATOM),'region'=>$region,'source_url'=>$regionUrl] as $k=>$v)$set->execute([$k,$v]);}
    $db->prepare('DELETE FROM or_prepare_queue WHERE region_key=?')->execute([$region]);
    $db->prepare('DELETE FROM or_journey_cache WHERE region_key=?')->execute([$region]);
    $db->prepare('DELETE FROM or_service_cache WHERE region_key=?')->execute([$region]);
    $db->commit();logline("Activated $regionLabel dataset $ds");
    if($oldDs>0&&$oldDs!==$ds){foreach(['or_stops','or_routes','or_trips','or_stop_times','or_service_dates','or_shapes'] as $table){$q=$db->prepare("DELETE FROM $table WHERE dataset_id=?");$q->execute([$oldDs]);}}
    logline('Old dataset rows removed. Update complete.');flock($lock,LOCK_UN);fclose($lock);
}catch(Throwable $e){fwrite(STDERR,'OpenRoad GTFS update failed: '.$e->getMessage().PHP_EOL);exit(1);}
