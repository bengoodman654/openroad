<?php
require_once __DIR__.'/../private/lib/bods_gateway.php';
function check(bool $ok,string $message):void{if(!$ok)throw new RuntimeException($message);}
$dir=sys_get_temp_dir().'/openroad-bods-test-'.bin2hex(random_bytes(4));mkdir($dir,0700);
$xml='<Siri><ServiceDelivery><VehicleMonitoringDelivery><VehicleActivity><RecordedAtTime>2026-10-15T12:00:00Z</RecordedAtTime></VehicleActivity></VehicleMonitoringDelivery></ServiceDelivery></Siri>';
$calls=0;
$fetch=function(string $url)use(&$calls,$xml):array{$calls++;check(str_starts_with($url,'https://data.bus-data.dft.gov.uk/api/v1/datafeed/?'),'canonical fixed host');return [200,$xml];};
[$s,$v]=openroad_bods_live('75',51.46,-2.59,$fetch,$dir,1234567890,'testvalidkey');check($s===200&&$v['ok']&&$calls===1,'initial fetch');
[$s,$v]=openroad_bods_live('75',51.463,-2.586,$fetch,$dir,1234567900,'testvalidkey');check($s===200&&$v['cache']==='hit'&&$calls===1,'cache reuse');
[$s,$v]=openroad_bods_live('<bad>',51.46,-2.59,$fetch,$dir,1234567900,'testvalidkey');check($s===400,'invalid line');
[$s,$v]=openroad_bods_live('75',40,-2,$fetch,$dir,1234567900,'testvalidkey');check($s===400,'invalid region');
[$s,$v]=openroad_bods_live('75',51.46,-2.59,$fetch,$dir,1234567955,'');check($s===503,'missing key');
for($i=1;$i<8;$i++){[$s,$v]=openroad_bods_live((string)(100+$i),51.46,-2.59,$fetch,$dir,1234567890,'testvalidkey');check($s===200,'upstream budget '.$i);}
[$s,$v]=openroad_bods_live('900',51.46,-2.59,$fetch,$dir,1234567890,'testvalidkey');check($s===429&&$calls===8,'hourly upstream cap');
// Diagnostic tests use injected upstream fixtures and never call BODS.
$failureDir=sys_get_temp_dir().'/openroad-bods-errors-'.bin2hex(random_bytes(4));
mkdir($failureDir,0700);
$blocked=function(string $url):array{return [406,'detail'];};
[$http,$reply]=openroad_bods_live('75',51.46,-2.59,$blocked,$failureDir,1234567890,'testvalidkey');
check($http===503 && str_contains($reply['error'],'HTTP 406'),'406 status must remain actionable');
$other=function(string $url):array{return [301,''];};
[$http,$reply]=openroad_bods_live('76',51.46,-2.59,$other,$failureDir,1234567890,'testvalidkey');
check($http===503 && str_contains($reply['error'],'redirected'),'301 status must identify bad canonical URL');
foreach(glob($failureDir.'/*') as $p)unlink($p);rmdir($failureDir);
foreach(glob($dir.'/*') as $p)unlink($p);rmdir($dir);
echo "BODS gateway: 8 upstream calls max, shared cache and validation: PASS\n";
