<?php
/**
 * ONE-SHOT, READ-ONLY BODS timetable-metadata inspection.
 * Run only by trusted GitHub workflow over SSH on the configured host.
 * No uploads, database access, cron, cache writes, credentials or raw responses in logs.
 */
if (PHP_SAPI !== 'cli') exit(2);
$root=$argv[1]??'';
$noc=$argv[2]??'';
if (!preg_match('~^/[A-Za-z0-9_./-]+$~D',$root) ||
    !in_array($noc,['TCVW','FBRI'],true)) {
    fwrite(STDERR,"Invalid operator or root.\n"); exit(2);
}
$path=rtrim($root,'/').'/provider-secrets.php';
if(!is_file($path)){echo "Metadata check: no server credential file.\n";exit(3);}
$settings=require $path;
$key=is_array($settings)?trim((string)($settings['bods_api_key']??'')):'';
if(!preg_match('/^[A-Za-z0-9._-]{8,256}$/D',$key)){
    echo "Metadata check: no valid BODS key configured.\n";exit(3);
}
$url='https://data.bus-data.dft.gov.uk/api/v1/dataset/?limit=50&noc='.$noc.
     '&status=published&api_key='.rawurlencode($key);
$ctx=stream_context_create([
 'http'=>[
   'method'=>'GET','header'=>"Accept: application/json\r\nUser-Agent: OpenRoad-PTv2-Metadata-Inspection/1.0\r\n",
   'timeout'=>5,'ignore_errors'=>true,'follow_location'=>0,'max_redirects'=>0
 ],
 'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false],
]);
$fp=@fopen($url,'rb',false,$ctx);
if($fp===false){echo "Metadata HTTP: CONNECTION_FAILED\n";exit(4);}
stream_set_timeout($fp,5);
$body=stream_get_contents($fp,524289);
$meta=stream_get_meta_data($fp);fclose($fp);
$status=0;
foreach(($meta['wrapper_data']??[]) as $header){
  if(preg_match('~^HTTP/\S+\s+(\d{3})\b~',$header,$m))$status=(int)$m[1];
}
echo "Metadata HTTP: ".$status."\n";
if($status!==200||!is_string($body)||strlen($body)>524288||($meta['timed_out']??false)){
    echo "Metadata result unavailable; no dataset files requested.\n";
    exit($status===401||$status===403?5:4);
}
$data=json_decode($body,true);
if(!is_array($data)||!is_array($data['results']??null)){
    echo "Metadata response schema unexpected.\n";exit(6);
}
$count=is_numeric($data['count']??null)?(int)$data['count']:null;
echo "Operator: ".$noc."\n";
echo "Returned records: ".count($data['results'])."; total count: ".($count??'unknown')."\n";
echo "Pagination may be incomplete: ".($count!==null&&$count>count($data['results'])?'yes':'unknown/no')."\n";
$wanted=$noc==='TCVW'?['11','12X','9']:['75'];
$matched=0;
foreach($data['results'] as $r){
 if(!is_array($r)||($r['status']??'')!=='published')continue;
 $codes=$r['noc']??[];if(is_string($codes))$codes=[$codes];
 if(!is_array($codes)||!in_array($noc,$codes,true))continue;
 $lines=$r['lines']??[];if(is_string($lines))$lines=[$lines];
 if(!is_array($lines))$lines=[];
 $found=array_values(array_intersect($wanted,array_map(
    static fn($x)=>strtoupper(trim((string)$x)),$lines)));
 if(!$found&&count($lines)>0)continue;
 $matched++;
 $id=$r['id']??null;
 $id=(is_int($id)||ctype_digit((string)$id))?(string)$id:'unknown';
 $name=substr(preg_replace('/[[:cntrl:]]/',' ',(string)($r['name']??'')),0,120);
 $agency=substr(preg_replace('/[[:cntrl:]]/',' ',(string)($r['operatorName']??'')),0,100);
 $raw=(string)($r['url']??'');
 $parts=@parse_url($raw);
 $clean='';
 if(is_array($parts)&&($parts['scheme']??'')==='https'&&
    !empty($parts['host'])&&!isset($parts['user'])&&!isset($parts['pass'])&&
    !isset($parts['query'])&&!isset($parts['fragment'])){
    $host=strtolower($parts['host']);
    if(preg_match('/^[a-z0-9.-]+$/D',$host)&&str_contains($host,'.')&&
       !str_ends_with($host,'.local')&&!str_ends_with($host,'.internal')){
       $path=sprintf('%s',($parts['path']??'/'));
       if(strlen($path)<=260&& !preg_match('/[[:cntrl:]]/',$path))
           $clean='https://'.$host.$path;
    }
 }
 echo json_encode([
    'id'=>$id,'datasetName'=>$name,'operator'=>$agency,
    'wantedLinesPresent'=>$found,'lineListEmpty'=>count($lines)===0,
    'dateFrom'=>$r['firstStartDate']??null,'dateTo'=>$r['lastEndDate']??null,
    'modified'=>$r['modified']??null,'downloadUrlWithoutQuery'=>$clean?:null
 ],JSON_INVALID_UTF8_SUBSTITUTE|JSON_UNESCAPED_SLASHES)."\n";
}
echo "Candidate datasets in this page: ".$matched."\n";
echo "No timetable files downloaded. No production service modified.\n";
