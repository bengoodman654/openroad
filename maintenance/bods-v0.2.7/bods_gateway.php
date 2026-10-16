<?php
/**
 * OpenRoad v0.2.7: area-only BODS SIRI-VM gateway, area feed filtering by LineRef or PublishedLineName.
 * IMPORTANT: no cron, no polling, no prefetch. Private server-side credential only.
 * One request at a time, 20/hour maximum, 256 KiB response bound, no background work.
 */
require_once __DIR__.'/bootstrap.php';

function openroad_bods_key(): string {
    $path=openroad_private_root().'/provider-secrets.php';
    if (!is_file($path)) return '';
    $settings=require $path;
    if (!is_array($settings)) return '';
    $key=trim((string)($settings['bods_api_key']??''));
    return preg_match('/^[A-Za-z0-9._-]{8,256}$/D',$key) ? $key : '';
}

/** Only fixed BODS HTTPS host is permitted. No redirects, max 256 KiB reply. */
function openroad_bods_fetch(string $url): array {
    if (!str_starts_with($url,'https://data.bus-data.dft.gov.uk/api/v1/datafeed/?')) return [0,''];
    $ctx=stream_context_create([
        'http'=>['method'=>'GET','header'=>"Accept: text/xml, application/xml;q=0.9, */*;q=0.8\r\nUser-Agent: OpenRoad/0.2.6\r\n",
                 'timeout'=>2.5,'ignore_errors'=>true,'follow_location'=>0,'max_redirects'=>0],
        'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false],
    ]);
    $fp=@fopen($url,'rb',false,$ctx);
    if ($fp===false) return [0,''];
    stream_set_timeout($fp,2,500000);
    $body=stream_get_contents($fp,262145);
    $meta=stream_get_meta_data($fp);
    fclose($fp);
    $status=0;
    foreach (($meta['wrapper_data']??[]) as $header) {
        if (preg_match('/^HTTP\/\S+\s+(\d{3})\b/',$header,$match)) $status=(int)$match[1];
    }
    if (!is_string($body) || strlen($body)>262144 || !empty($meta['timed_out'])) return [0,''];
    return [$status,$body];
}

function openroad_bods_cache_read(string $path,int $now): ?array {
    if (!is_file($path) || @filesize($path)>350000) return null;
    $entry=json_decode((string)@file_get_contents($path),true);
    if (!is_array($entry)||($entry['expires']??0)<=$now||!is_array($entry['reply']??null))return null;
    return $entry['reply'];
}
function openroad_bods_cache_last_known(string $path,int $now): ?array {
    if(!is_file($path) || @filesize($path)>350000) return null;
    $entry=json_decode((string)@file_get_contents($path),true);
    $reply=$entry['reply']??null;
    if(!is_array($reply) || !($reply['ok']??false)) return null;
    $checked=strtotime((string)($reply['checkedAt']??''));
    if($checked===false || $checked>$now+60 || $now-$checked>900) return null;
    return $reply;
}

function openroad_bods_cache_write(string $path,array $reply,int $expires): void {
    $json=json_encode(['expires'=>$expires,'reply'=>$reply],JSON_INVALID_UTF8_SUBSTITUTE);
    if (!is_string($json)||strlen($json)>350000)return;
    $tmp=@tempnam(dirname($path),'bods');
    if($tmp===false)return;
    @chmod($tmp,0600);
    if(@file_put_contents($tmp,$json,LOCK_EX)===false||!@rename($tmp,$path))@unlink($tmp);
}

/** Filter the area feed to the requested LineRef while preserving the SIRI envelope. */
function openroad_bods_filter_line(array $raw,string $line,string $cache): array {
    if (!($raw['ok']??false)) return [503,array_merge($raw,['cache'=>$cache])];
    if (!class_exists('DOMDocument')) return [503,['ok'=>false,'error'=>'XML parser unavailable','cache'=>$cache]];
    $dom=new DOMDocument();
    $old=libxml_use_internal_errors(true);
    try {
        if (!$dom->loadXML((string)($raw['xml']??''),LIBXML_NONET)) return [503,['ok'=>false,'error'=>'Invalid BODS XML','cache'=>$cache]];
        $xp=new DOMXPath($dom);
        $nodes=$xp->query('//*[local-name()="VehicleActivity"]');
        if ($nodes===false) return [503,['ok'=>false,'error'=>'Invalid BODS XML','cache'=>$cache]];
        foreach(iterator_to_array($nodes) as $activity){
            $refs=$xp->query('.//*[local-name()="MonitoredVehicleJourney"]/*[local-name()="LineRef" or local-name()="PublishedLineName"]',$activity);
            $matched=false;
            if($refs!==false)foreach($refs as $ref){
                if(strcasecmp(trim($ref->textContent),trim($line))===0){$matched=true;break;}
            }
            if(!$matched)$activity->parentNode?->removeChild($activity);
        }
        $xml=$dom->saveXML();
        if(!is_string($xml))return [503,['ok'=>false,'error'=>'Invalid BODS XML','cache'=>$cache]];
        return [200,['ok'=>true,'line'=>$line,'source'=>'BODS','xml'=>$xml,'checkedAt'=>$raw['checkedAt']??gmdate('c'),'cache'=>$cache]];
    } finally { libxml_clear_errors();libxml_use_internal_errors($old); }
}

/** Returns [HTTP status, JSON object]. $fetch and $keyOverride exist ONLY for offline tests. */
function openroad_bods_live(string $line,float $lat,float $lon,?callable $fetch=null,?string $cacheDir=null,?int $now=null,?string $keyOverride=null): array {
    $line=trim($line);
    if (!preg_match('/^[A-Za-z0-9 _-]{1,12}$/D',$line))return [400,['ok'=>false,'error'=>'Invalid bus line']];
    if (!is_finite($lat)||!is_finite($lon)||$lat<49.7||$lat>56.2||$lon< -6.8||$lon>2.2)
        return [400,['ok'=>false,'error'=>'BODS live data is only available for England']];
    $key=$keyOverride??openroad_bods_key();
    if ($key==='')return [503,['ok'=>false,'error'=>'BODS is not configured on the OpenRoad server']];
    $now=$now??time();
    $dir=$cacheDir??openroad_private_root().'/cache/bods-v1';
    if (!is_dir($dir)&&!@mkdir($dir,0700,true)&&!is_dir($dir))
        return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
    // Budget and lock remain in the v1 directory: never reset the hourly count.
    // Keep coarsely tiled v3 cache separate from v2 per-coordinate cache.
    $areaDir=$dir.'/area-v3';
    if (!is_dir($areaDir)&&!@mkdir($areaDir,0700,true)&&!is_dir($areaDir))
        return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
    // 0.05-degree tile centres: repeated route searches within an area share one response.
    // The 0.06-degree bounding box covers all locations assigned to a tile.
    $lat=round((floor($lat*20)+0.5)/20,3);
    $lon=round((floor($lon*20)+0.5)/20,3);
    $cacheKey=hash('sha256','area-v3|'.number_format($lat,3,'.','').'|'.number_format($lon,3,'.',''));
    $path=$areaDir.'/'.$cacheKey.'.json';
    $hit=openroad_bods_cache_read($path,$now);
    if ($hit!==null)return openroad_bods_filter_line($hit,$line,'hit');
    $lock=@fopen($dir.'/bods.lock','c');
    if($lock===false)return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
    if(!flock($lock,LOCK_EX|LOCK_NB)){fclose($lock);return [503,['ok'=>false,'error'=>'Live buses are busy; retry shortly']];}
    try {
        $hit=openroad_bods_cache_read($path,$now);
        if($hit!==null)return openroad_bods_filter_line($hit,$line,'hit');
        // Up to 32 cached v2 geographical tiles, capped at ~11 MB worst case.
        if(!is_file($path)) {
            $entries=glob($areaDir.'/*.json')?:[];
            foreach($entries as $entry){
                if(basename($entry)==='budget.json')continue;
                if(@filemtime($entry)<$now-3600)@unlink($entry);
            }
            $entries=array_filter(glob($areaDir.'/*.json')?:[],static fn($entry)=>preg_match('/^[a-f0-9]{64}\.json$/D',basename($entry))===1);
            if(count($entries)>=32)return [429,['ok'=>false,'error'=>'Live bus cache capacity reached']];
        }
        $hour=intdiv($now,3600);
        $budgetFile=$dir.'/budget.json';
        $budget=json_decode((string)@file_get_contents($budgetFile),true);
        $count=is_array($budget)&&($budget['hour']??null)===$hour?(int)($budget['count']??0):0;
        if($count>=20){
            $older=openroad_bods_cache_last_known($path,$now);
            if($older!==null)return openroad_bods_filter_line($older,$line,'stale');
            $mins=max(1,(int)ceil((($hour+1)*3600-$now)/60));
            return [429,['ok'=>false,'error'=>'Live bus hourly request limit reached; try again in '.$mins.' minutes']];
        }
        $tmp=@tempnam($dir,'budget');
        if($tmp===false)return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
        @chmod($tmp,0600);
        if(@file_put_contents($tmp,json_encode(['hour'=>$hour,'count'=>$count+1]),LOCK_EX)===false||!@rename($tmp,$budgetFile)){
            @unlink($tmp);return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
        }
        $pad=0.06;
        $bbox=sprintf('%.5f,%.5f,%.5f,%.5f',$lon-$pad,$lat-$pad,$lon+$pad,$lat+$pad);
        $url='https://data.bus-data.dft.gov.uk/api/v1/datafeed/?boundingBox='.rawurlencode($bbox)
             .'&api_key='.rawurlencode($key);
        try{[$status,$body]=($fetch??'openroad_bods_fetch')($url);}catch(Throwable $ignored){$status=0;$body='';}
        if($status!==200||!is_string($body)||strlen($body)>262144||strlen($body)<40||!
            (str_contains($body,'VehicleMonitoringDelivery')||str_contains($body,'Siri'))){
            // No credentials, query URL, personal location or upstream response body
            // are returned to the phone. Expose only bounded, actionable failure classes.
            if ($status===401||$status===403) $reason='BODS rejected the server key or its access permissions (HTTP '.$status.')';
            elseif ($status===406) $reason='BODS rejected the vehicle feed request (HTTP 406)';
            elseif ($status>=300&&$status<400) $reason='BODS redirected the vehicle feed; endpoint update required (HTTP '.$status.')';
            elseif ($status===0) $reason='Could not connect to the BODS live vehicle service';
            elseif ($status>=500) $reason='BODS live vehicle service temporarily unavailable (HTTP '.$status.')';
            else $reason='BODS returned no usable live vehicle data (HTTP '.$status.')';
            $bad=['ok'=>false,'error'=>$reason];
            openroad_bods_cache_write($path,$bad,$now+45);
            return [503,$bad];
        }
        $result=['ok'=>true,'source'=>'BODS','xml'=>$body,'checkedAt'=>gmdate('c',$now)];
        $filtered=openroad_bods_filter_line($result,$line,'miss');
        if($filtered[0]!==200)return $filtered;
        openroad_bods_cache_write($path,$result,$now+150);
        return $filtered;
    }finally{flock($lock,LOCK_UN);fclose($lock);}
}
