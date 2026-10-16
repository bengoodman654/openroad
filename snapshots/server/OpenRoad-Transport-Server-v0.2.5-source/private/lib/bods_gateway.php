<?php
/**
 * OpenRoad v0.2.5: strictly on-demand BODS SIRI-VM gateway.
 * IMPORTANT: no cron, no polling, no prefetch. Private server-side credential only.
 * Bounds + budget defend other websites/email on shared JustHostMe hosting.
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
function openroad_bods_cache_write(string $path,array $reply,int $expires): void {
    $json=json_encode(['expires'=>$expires,'reply'=>$reply],JSON_INVALID_UTF8_SUBSTITUTE);
    if (!is_string($json)||strlen($json)>350000)return;
    $tmp=@tempnam(dirname($path),'bods');
    if($tmp===false)return;
    @chmod($tmp,0600);
    if(@file_put_contents($tmp,$json,LOCK_EX)===false||!@rename($tmp,$path))@unlink($tmp);
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
    // Round query coordinates to ~1 km tiles to reuse same live feed nearby.
    $lat=round($lat,2);$lon=round($lon,2);
    $cacheKey=hash('sha256',strtoupper($line).'|'.number_format($lat,2,'.','').'|'.number_format($lon,2,'.',''));
    $path=$dir.'/'.$cacheKey.'.json';
    $hit=openroad_bods_cache_read($path,$now);
    if ($hit!==null)return [($hit['ok']??false)?200:503,$hit+['cache'=>'hit']];
    $lock=@fopen($dir.'/bods.lock','c');
    if($lock===false)return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
    if(!flock($lock,LOCK_EX|LOCK_NB)){fclose($lock);return [503,['ok'=>false,'error'=>'Live buses are busy; retry shortly']];}
    try {
        $hit=openroad_bods_cache_read($path,$now);
        if($hit!==null)return [($hit['ok']??false)?200:503,$hit+['cache'=>'hit']];
        // Up to 32 cached geographical tiles, capped at ~11 MB worst case.
        if(!is_file($path)) {
            $entries=glob($dir.'/*.json')?:[];
            foreach($entries as $entry){
                if(basename($entry)==='budget.json')continue;
                if(@filemtime($entry)<$now-3600)@unlink($entry);
            }
            $entries=array_filter(glob($dir.'/*.json')?:[],static fn($entry)=>preg_match('/^[a-f0-9]{64}\.json$/D',basename($entry))===1);
            if(count($entries)>=32)return [429,['ok'=>false,'error'=>'Live bus cache capacity reached']];
        }
        $hour=intdiv($now,3600);
        $budgetFile=$dir.'/budget.json';
        $budget=json_decode((string)@file_get_contents($budgetFile),true);
        $count=is_array($budget)&&($budget['hour']??null)===$hour?(int)($budget['count']??0):0;
        if($count>=8)return [429,['ok'=>false,'error'=>'Live bus hourly request budget reached']];
        $tmp=@tempnam($dir,'budget');
        if($tmp===false)return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
        @chmod($tmp,0600);
        if(@file_put_contents($tmp,json_encode(['hour'=>$hour,'count'=>$count+1]),LOCK_EX)===false||!@rename($tmp,$budgetFile)){
            @unlink($tmp);return [503,['ok'=>false,'error'=>'Live bus service is unavailable']];
        }
        $pad=0.04;
        $bbox=sprintf('%.5f,%.5f,%.5f,%.5f',$lon-$pad,$lat-$pad,$lon+$pad,$lat+$pad);
        $url='https://data.bus-data.dft.gov.uk/api/v1/datafeed/?boundingBox='.rawurlencode($bbox)
             .'&lineRef='.rawurlencode($line).'&api_key='.rawurlencode($key);
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
        $result=['ok'=>true,'line'=>$line,'source'=>'BODS','xml'=>$body,'checkedAt'=>gmdate('c',$now)];
        openroad_bods_cache_write($path,$result,$now+60);
        return [200,$result+['cache'=>'miss']];
    }finally{flock($lock,LOCK_UN);fclose($lock);}
}
