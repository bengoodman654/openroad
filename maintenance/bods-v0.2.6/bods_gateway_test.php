<?php
/** All tests use injected fixtures. No test makes an upstream API request. */
require_once __DIR__.'/../private/lib/bods_gateway.php';
function verify(bool $condition,string $message): void {
    if (!$condition) throw new RuntimeException($message);
}
function freshDir(): string {
    $dir=sys_get_temp_dir().'/openroad-bods-026-'.bin2hex(random_bytes(5));
    verify(mkdir($dir,0700),'create test directory');
    return $dir;
}
function cleanDir(string $path): void {
    foreach (glob($path.'/*')?:[] as $file) {
        if (is_dir($file)) cleanDir($file); else unlink($file);
    }
    rmdir($path);
}
$xml='<Siri><ServiceDelivery><VehicleMonitoringDelivery>'.
     '<VehicleActivity><MonitoredVehicleJourney><LineRef>75</LineRef></MonitoredVehicleJourney></VehicleActivity>'.
     '<VehicleActivity><MonitoredVehicleJourney><LineRef>76</LineRef></MonitoredVehicleJourney></VehicleActivity>'.
     '</VehicleMonitoringDelivery></ServiceDelivery></Siri>';
$dir=freshDir(); $calls=0;
$fetch=function(string $url)use(&$calls,$xml):array{
    $calls++;
    verify(str_starts_with($url,'https://data.bus-data.dft.gov.uk/api/v1/datafeed/?'),'fixed BODS endpoint');
    verify(str_contains($url,'boundingBox='),'geographical query');
    verify(str_contains($url,'&api_key='),'credential in upstream query');
    verify(!str_contains($url,'lineRef='),'never use rejected route filter');
    return [200,$xml];
};
[$status,$reply]=openroad_bods_live('75',51.46,-2.59,$fetch,$dir,1234567890,'testvalidkey');
verify($status===200 && $reply['ok'] && $reply['line']==='75' && $reply['xml']===$xml && $reply['cache']==='miss' && $calls===1,'first area fetch');
[$status,$reply]=openroad_bods_live('76',51.463,-2.586,$fetch,$dir,1234567900,'testvalidkey');
verify($status===200 && $reply['line']==='76' && $reply['xml']===$xml && $reply['cache']==='hit' && $calls===1,'different route shares same area response');
verify(is_dir($dir.'/area-v2'),'versioned area-only cache exists');
[$status,$reply]=openroad_bods_live('<bad>',51.46,-2.59,$fetch,$dir,1234567900,'testvalidkey');
verify($status===400,'reject invalid line');
[$status,$reply]=openroad_bods_live('75',40,-2.59,$fetch,$dir,1234567900,'testvalidkey');
verify($status===400,'reject location outside England');
[$status,$reply]=openroad_bods_live('75',51.46,-2.59,$fetch,$dir,1234567900,'');
verify($status===503,'reject missing credential');
// Seven fresh areas + original area consume precisely eight calls this hour.
for($i=1;$i<8;$i++){
    [$status,$reply]=openroad_bods_live('75',51.46+$i*0.02,-2.59,$fetch,$dir,1234567890,'testvalidkey');
    verify($status===200 && $reply['cache']==='miss','budgeted area fetch '.$i);
}
[$status,$reply]=openroad_bods_live('900',51.66,-2.59,$fetch,$dir,1234567890,'testvalidkey');
verify($status===429 && $calls===8,'eight-call hourly cap enforced across areas');
// Failure response is shared across lines but must expire within 45 seconds.
$failureDir=freshDir();$failedCalls=0;
$blocked=function(string $url)use(&$failedCalls):array{$failedCalls++;return [406,'detail'];};
[$s,$r]=openroad_bods_live('75',51.46,-2.59,$blocked,$failureDir,1234567890,'testvalidkey');
verify($s===503&&str_contains($r['error'],'HTTP 406'),'upstream failure surfaced');
[$s,$r]=openroad_bods_live('76',51.46,-2.59,$blocked,$failureDir,1234567900,'testvalidkey');
verify($s===503&&$r['cache']==='hit'&&$failedCalls===1,'error cache shared across lines');
[$s,$r]=openroad_bods_live('75',51.46,-2.59,$blocked,$failureDir,1234567936,'testvalidkey');
verify($s===503&&$failedCalls===2,'error cache expires');
$originalBudget=freshDir();
file_put_contents($originalBudget.'/budget.json',json_encode(['hour'=>intdiv(1234567890,3600),'count'=>8]));
$notCalled=0;
$mustNotFetch=function(string $url)use(&$notCalled):array{$notCalled++;return [200,'unused'];};
[$s,$r]=openroad_bods_live('75',51.46,-2.59,$mustNotFetch,$originalBudget,1234567890,'testvalidkey');
verify($s===429 && $notCalled===0,'v1 hourly budget remains effective with v2 cache');
$oversizedDir=freshDir();
[$s,$r]=openroad_bods_live('75',51.46,-2.59,static fn(string $u):array=>[200,str_repeat('x',262145)],$oversizedDir,1234567890,'testvalidkey');
verify($s===503,'reject overlarge response');
foreach([$dir,$failureDir,$originalBudget,$oversizedDir] as $d)cleanDir($d);
echo "BODS v0.2.6: shared area cache, per-line labels, rejection filtering, expiry, hourly budget, payload bounds: PASS\n";
