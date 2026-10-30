<?php
/**
 * OpenRoad Rail Data proxy – v0.2.4. No cron, no bulk downloads.
 * All third-party credentials live in private/provider-secrets.php OUTSIDE public_html.
 * No endpoint redirects, external URLs, private keys or arbitrary filters accepted from clients.
 */
require_once __DIR__ . '/bootstrap.php';

function openroad_rail_key(): string {
    $path=openroad_private_root().'/provider-secrets.php';
    if (!is_file($path)) return '';
    $settings=require $path;
    if(!is_array($settings)) return '';
    $key=trim((string)($settings['raildata_consumer_key']??''));
    return preg_match('/^[A-Za-z0-9._\-]{10,256}$/D',$key)?$key:'';
}

function openroad_rail_fetch(string $url, string $key): array {
    // Fixed, HTTPS-only upstream. STREAM wrapper works without php-curl installed.
    $prefix='https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/';
    if (!str_starts_with($url,$prefix)) return [0,''];
    $context=stream_context_create([
        'http'=>['method'=>'GET','header'=>"Accept: application/json\r\nx-apikey: ".$key."\r\nUser-Agent: OpenRoad/0.2.4\r\n",
                 'timeout'=>2.5,'ignore_errors'=>true,'follow_location'=>0,'max_redirects'=>0],
        'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false],
    ]);
    $fp=@fopen($url,'rb',false,$context);
    if($fp===false)return [0,''];
    stream_set_timeout($fp,2,500000);
    $body=stream_get_contents($fp,65537);
    $meta=stream_get_meta_data($fp);
    fclose($fp);
    $code=0;
    foreach(($meta['wrapper_data']??[]) as $h){
        if(preg_match('/^HTTP\/\S+\s+(\d{3})\b/',$h,$m))$code=(int)$m[1];
    }
    if($body===false || strlen($body)>65536 || !empty($meta['timed_out']))return [0,''];
    return [$code,$body];
}

function openroad_rail_truncate(string $s,int $length): string {
    if(preg_match('/^.{0,'.$length.'}/us',$s,$m))return $m[0];
    return '';
}

function openroad_rail_response(string $crs, array $raw): ?array {
    $board=is_array($raw['GetDepartureBoardResult']??null)?$raw['GetDepartureBoardResult']:
           (is_array($raw['stationBoard']??null)?$raw['stationBoard']:$raw);
    $services=$board['trainServices']??null;
    if(!is_array($services))return null;
    $rows=[];
    foreach(array_slice($services,0,40) as $service){
        if(!is_array($service))continue;
        $destinations=$service['destination']??[];
        $first=is_array($destinations) ? (isset($destinations[0])?($destinations[0]??[]):$destinations) : [];
        $destination=is_array($first)?(string)($first['locationName']??'Unknown destination'):'Unknown destination';
        $etd=substr((string)($service['etd']??''),0,50);
        // Some licensed live-board responses include calling-point lists.
        // They are optional: never infer missing stops from an unrelated train.
        $calling=[];
        $visit=static function($value)use (&$calling,&$visit):void{
            if(!is_array($value)||count($calling)>=48)return;
            if(isset($value['crs'])&&preg_match('/^[A-Z]{3}$/D',(string)$value['crs']))
                $calling[]=(string)$value['crs'];
            foreach($value as $key=>$member){
                if(is_array($member)&&count($calling)<48)$visit($member);
            }
        };
        if(isset($service['subsequentCallingPoints']))$visit($service['subsequentCallingPoints']);
        $rows[]=['std'=>substr((string)($service['std']??''),0,12),
                 'etd'=>$etd,
                 'platform'=>substr((string)($service['platform']??''),0,16),
                 'destination'=>openroad_rail_truncate($destination,100),
                 'destinationCrs'=>is_array($first)?substr((string)($first['crs']??''),0,3):'',
                 'serviceID'=>substr((string)($service['serviceID']??''),0,128),
                 'callingCrs'=>array_values(array_unique($calling)),
                 'operator'=>openroad_rail_truncate((string)($service['operator']??''),90),
                 'cancelled'=>!empty($service['isCancelled'])||strtolower($etd)==='cancelled'];
    }
    return ['station'=>$crs,'stationName'=>openroad_rail_truncate((string)($board['locationName']??$crs),100),
            'services'=>$rows,'source'=>'Rail Data Marketplace'];
}

function openroad_rail_cache_read(string $path, int $now): ?array {
    if(!is_file($path) || @filesize($path)>20000)return null;
    $row=json_decode((string)@file_get_contents($path),true);
    if(!is_array($row) || (int)($row['expires']??0)<=$now || !is_array($row['response']??null))return null;
    return $row['response'];
}
function openroad_rail_cache_write(string $path,array $payload,int $expiry): void {
    $json=json_encode(['expires'=>$expiry,'response'=>$payload],JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
    if($json===false || strlen($json)>20000)return;
    $temp=@tempnam(dirname($path),'rail');
    if($temp===false)return;
    @chmod($temp,0600);
    if(@file_put_contents($temp,$json,LOCK_EX)===false || !@rename($temp,$path))@unlink($temp);
}

/** Return HTTP status and safe response. $fetch is optional test injection, never client-controlled. */
function openroad_rail_board(string $crs,?callable $fetch=null,?string $cacheDir=null,?int $now=null,?string $keyOverride=null,?int $timeOffset=null,int $numRows=8): array {
    $crs=strtoupper(trim($crs));
    if(!preg_match('/^[A-Z]{3}$/D',$crs))return [400,['ok'=>false,'error'=>'Invalid station code']];
    $key=$keyOverride??openroad_rail_key();
    if($key==='')return [503,['ok'=>false,'error'=>'Rail Data is not configured on the OpenRoad server']];
    $now=$now??time();
    if($timeOffset!==null && ($timeOffset < -119 || $timeOffset > 119))return [400,['ok'=>false,'error'=>'Invalid train time']];
    if($numRows<1||$numRows>40)return [400,['ok'=>false,'error'=>'Invalid requested board size']];
    $offset=$timeOffset??0;
    $dir=$cacheDir??openroad_private_root().'/cache/rail-v1';
    if(!is_dir($dir) && !@mkdir($dir,0700,true) && !is_dir($dir))return [503,['ok'=>false,'error'=>'Rail departure service is unavailable']];
    $path=$dir.'/'.$crs.($timeOffset===null?'':'-'.($offset<0?'m'.abs($offset):'p'.$offset).'-'.$numRows).'.json';
    $cache=openroad_rail_cache_read($path,$now);
    if($cache!==null)return [($cache['ok']??false)?200:503,$cache+['cache'=>'hit']];
    $lock=@fopen($dir.'/rail.lock','c');
    if($lock===false)return [503,['ok'=>false,'error'=>'Rail departure service is unavailable']];
    if(!flock($lock,LOCK_EX|LOCK_NB)){
        fclose($lock);
        return [503,['ok'=>false,'error'=>'Rail service is busy; retry shortly']];
    }
    try {
        // Recheck cache inside lock: parallel requests must not trigger duplicate upstream calls.
        $cache=openroad_rail_cache_read($path,$now);
        if($cache!==null)return [($cache['ok']??false)?200:503,$cache+['cache'=>'hit']];
        // Cap the on-disk rail cache to 64 stations (<1.3 MB). Prune old entries
        // only when handling a cache miss, not on every Android request.
        if(!is_file($path)) {
            $entries=glob($dir.'/*.json')?:[];
            $entries=array_values(array_filter($entries,static fn($p)=>preg_match('/\/[A-Z]{3}(?:-[mp]\d+-\d+)?\.json$/D',$p)));
            if(count($entries)>=96){
                foreach($entries as $entry){
                    if(@filemtime($entry)<$now-86400)@unlink($entry);
                }
                if(count(array_filter(glob($dir.'/*.json')?:[],static fn($p)=>preg_match('/\/[A-Z]{3}(?:-[mp]\d+-\d+)?\.json$/D',$p)))>=96)
                    return [429,['ok'=>false,'error'=>'Rail cache capacity reached; retry later']];
            }
        }
        $budgetFile=$dir.'/budget.json';
        $budget=json_decode((string)@file_get_contents($budgetFile),true);
        $hour=intdiv($now,3600);
        $count=(is_array($budget)&&($budget['hour']??null)===$hour)?(int)($budget['count']??0):0;
        if($count>=12)return [429,['ok'=>false,'error'=>'Rail provider hourly budget reached; try again later']];
        // Consume quota BEFORE fetching. A failure also consumes a slot, preventing retry storms.
        $tmp=@tempnam($dir,'budget');
        if($tmp===false)return [503,['ok'=>false,'error'=>'Rail departure service is unavailable']];
        @chmod($tmp,0600);
        $written=@file_put_contents($tmp,json_encode(['hour'=>$hour,'count'=>$count+1]),LOCK_EX);
        if($written===false || !@rename($tmp,$budgetFile)){
            @unlink($tmp);
            return [503,['ok'=>false,'error'=>'Rail departure service is unavailable']];
        }
        $url='https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/'.$crs.'?numRows='.$numRows.'&timeOffset='.$offset.'&timeWindow=120';
        try{[$status,$body]=($fetch??'openroad_rail_fetch')($url,$key);}catch(Throwable $ignored){$status=0;$body='';}
        if($status!==200 || !is_string($body) || strlen($body)>65536){
            openroad_rail_cache_write($path,['ok'=>false,'error'=>'Rail Data is temporarily unavailable'], $now+45);
            return [503,['ok'=>false,'error'=>'Rail Data is temporarily unavailable']];
        }
        $data=json_decode($body,true,64);
        $result=is_array($data)?openroad_rail_response($crs,$data):null;
        if($result===null){
            openroad_rail_cache_write($path,['ok'=>false,'error'=>'Rail Data returned an unexpected response'],$now+45);
            return [503,['ok'=>false,'error'=>'Rail Data returned an unexpected response']];
        }
        $result['ok']=true;
        $result['checkedAt']=gmdate('c',$now);
        openroad_rail_cache_write($path,$result,$now+120);
        return [200,$result+['cache'=>'miss']];
    } finally {
        flock($lock,LOCK_UN);
        fclose($lock);
    }
}
