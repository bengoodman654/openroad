<?php
require_once __DIR__.'/../private/lib/rail_gateway.php';
function chk(bool $ok,string $message):void {if(!$ok){fwrite(STDERR,"FAIL $message\n");exit(1);}echo "OK $message\n";}
$cache=sys_get_temp_dir().'/openroad-rail-test-'.bin2hex(random_bytes(6));
mkdir($cache,0700,true);
$key='abcdef01234567890123456789012345';$calls=0;
$fetch=function($url,$k)use(&$calls,$key){$calls++;chk($k===$key,'key stays on server side');chk(str_contains($url,'GetDepartureBoard/BRI'),'fixed URL/allowed CRS');return [200,json_encode(['locationName'=>'Bristol Temple Meads','trainServices'=>[['std'=>'14:23','etd'=>'On time','destination'=>[['locationName'=>'Cardiff Central']],'platform'=>'5']]])];};
[$s,$r]=openroad_rail_board(' X ', $fetch,$cache,100,$key);chk($s===400,'invalid code rejects before contacting upstream');
[$s,$r]=openroad_rail_board('bri',$fetch,$cache,3601,$key);chk($s===200&&$r['station']==='BRI'&&count($r['services'])===1,'Rail Data converted to minimal departure board');
[$s,$r]=openroad_rail_board('BRI',$fetch,$cache,3620,$key);chk($s===200&&$calls===1,'cache suppresses duplicate upstream calls');
[$s,$r]=openroad_rail_board('BRI',$fetch,$cache,3722,$key);chk($s===200&&$calls===2,'cache expiry triggers refresh');
// A new distinct station uses a failing mock. Confirm 45-second negative caching.
$failure=function($url,$key)use(&$calls){$calls++;return [500,'<html>upstream failure</html>'];};
[$s,$r]=openroad_rail_board('LDS',$failure,$cache,3730,$key);chk($s===503,'upstream 500 is bounded error');
[$s,$r]=openroad_rail_board('LDS',$failure,$cache,3740,$key);chk($s===503&&$calls===3,'negative cache prevents retry storms');
// Force 12 fetches in one hour; 13th must not contact upstream.
for($i=0;$i<9;$i++)openroad_rail_board('A'.chr(65+$i).'B',$failure,$cache,3750,$key);
[$s,$r]=openroad_rail_board('ZZZ',$failure,$cache,3750,$key);chk($s===429&&$calls===12,'12 requests/h server-wide budget is enforced');
[$s,$r]=openroad_rail_board('BRI',$fetch,$cache,3750,$key);chk($s===200&&$calls===12,'cached data still works when budget exhausted');
// No provider configured => no upstream connection even when a cache exists.
[$s,$r]=openroad_rail_board('BRI',$fetch,$cache,3750,'');chk($s===503,'missing private provider key fails closed');
foreach(glob($cache.'/*') as $f) unlink($f);rmdir($cache);
