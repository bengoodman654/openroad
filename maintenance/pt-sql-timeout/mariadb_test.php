<?php
/** Disposable MariaDB-only regression, no network/API credentials or user data. */
declare(strict_types=1);
$root=$argv[1]??null;
if(!is_string($root)||!is_file($root.'/private/lib/router.php'))exit(2);
date_default_timezone_set('Europe/London');
$db=new PDO('mysql:host=127.0.0.1;port=3306;dbname=openroad_fixture;charset=utf8mb4','openroad_test','only-for-ci',
    [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
     PDO::ATTR_EMULATE_PREPARES=>true]);
$schema=file_get_contents($root.'/private/schema.sql');
if(!is_string($schema))throw new RuntimeException('Missing schema');
foreach(preg_split('/;\s*(?:\r?\n|$)/',$schema) as $s){$s=trim($s);if($s!=='')$db->exec($s);}
file_put_contents($root.'/private/config.php','<?php return '.var_export([
    'db_host'=>'127.0.0.1','db_name'=>'openroad_fixture','db_user'=>'openroad_test',
    'db_password'=>'only-for-ci','timezone'=>'Europe/London',
    'regions'=>['south_west'=>[
       'bbox'=>[50.0,-3.5,52.0,-1.0],'label'=>'Synthetic Bristol','permanent'=>true
    ]]
],true).';');
require_once $root.'/private/lib/router.php';
function test(bool $good,string $message):void {
    if(!$good)throw new RuntimeException('FAILED: '.$message);
    echo 'PASS: '.$message.PHP_EOL;
}
$ds=770077;$date=date('Y-m-d');$now=or_current_seconds();
$db->prepare('INSERT INTO or_regions(region_key,dataset_id,label,updated_at,last_used_at,permanent) VALUES(?,?,?,NOW(),NOW(),1)')
    ->execute(['south_west',$ds,'synthetic']);
$stops=[
    ['A','Near origin',51.44000,-2.60000],
    ['C','Transfer stop',51.45200,-2.60700],
    ['B','Near destination',51.46000,-2.61000],
    ['X','Unrelated route stop',51.49000,-2.63000]
];
$st=$db->prepare('INSERT INTO or_stops(dataset_id,stop_id,stop_name,stop_lat,stop_lon) VALUES(?,?,?,?,?)');
foreach($stops as $r)$st->execute([$ds,...$r]);
$routes=$db->prepare('INSERT INTO or_routes(dataset_id,route_id,short_name,long_name,route_type) VALUES(?,?,?,?,?)');
foreach(['D'=>'D','T1'=>'12','T2'=>'18','Z'=>'Z'] as $id=>$short)$routes->execute([$ds,$id,$short,$short.' synthetic','3']);
$trips=$db->prepare('INSERT INTO or_trips(dataset_id,trip_id,route_id,service_id,shape_id,headsign,direction_id) VALUES(?,?,?,?,?,?,?)');
foreach([
    ['D','D','ACTIVE','B'],['T1','T1','ACTIVE','C'],
    ['T2','T2','ACTIVE','B'],['Z','Z','INACTIVE','B']
] as $r)$trips->execute([$ds,$r[0],$r[1],$r[2],'',$r[3],'0']);
$db->prepare('INSERT INTO or_service_dates(dataset_id,service_id,service_date) VALUES(?,?,?)')
    ->execute([$ds,'ACTIVE',$date]);
$times=$db->prepare('INSERT INTO or_stop_times(dataset_id,trip_id,stop_id,stop_sequence,arrival_sec,departure_sec) VALUES(?,?,?,?,?,?)');
foreach([
    ['D','A',1,600], ['D','B',2,1800],
    ['T1','A',1,400], ['T1','C',2,850],
    ['T2','C',1,1200], ['T2','B',2,1900],
    ['Z','A',1,300], ['Z','B',2,700]
] as $r)$times->execute([$ds,$r[0],$r[1],$now+$r[3],$now+$r[3]]);
$origin=['A'=>['stop_id'=>'A','distance'=>2.0]];
$dest=['B'=>['stop_id'=>'B','distance'=>2.0]];
$direct=or_direct_candidates($db,$ds,$origin,$dest,$now,7200);
test(count($direct)===1,'direct candidates limited to active service');
test($direct[0]['trip_id']==='D' && $direct[0]['alight_stop']==='B',
     'direct alighting correctly matched to same trip and later stop');
$seeds=or_first_leg_seeds($db,$ds,$origin,$now,1.35,3600,3500);
test(isset($seeds['C'])&&count($seeds['C'])>0,
     'first-leg transfer stop derived from bounded active trip');
$second=or_second_leg_candidates($db,$ds,$seeds,$dest,$now,180,2000);
test(count(array_filter($second,static fn($r)=>$r['trip_id']==='T2'
      &&$r['transfer_stop']==='C'&&$r['alight_stop']==='B'))===1,
     'second-leg candidate preserves physical transfer order');
$directResult=openroad_plan_bus($db,51.44,-2.60,51.46,-2.61,
    ['phase'=>'full','maxWalk'=>10,'resultLimit'=>3]);
test(count($directResult['routes'])===1,
     'full phase returns direct route without expensive transfer refinement');
test(($directResult['routes'][0]['clearRouteTransit']??false)===true,
     'direct journey retains expected app navigation JSON shape');
$db->prepare('DELETE FROM or_stop_times WHERE dataset_id=? AND trip_id=?')
   ->execute([$ds,'D']);
$db->prepare('DELETE FROM or_journey_cache WHERE dataset_id=?')->execute([$ds]);
$transferResult=openroad_plan_bus($db,51.44,-2.60,51.46,-2.61,
    ['phase'=>'fast','maxWalk'=>10,'resultLimit'=>3]);
test(count($transferResult['routes'])>=1,
     'transfer journey is found when direct journey is absent');
test(count(array_filter($transferResult['routes'][0]['transitLegs'],
     static fn($leg)=>($leg['mode']??null)==='bus'))===2,
     'two distinct bus legs retained in selected transfer journey');
// Explicitly assert that unsafe/inactive direct trip does not appear.
test(!str_contains(json_encode($transferResult,JSON_THROW_ON_ERROR),'INACTIVE'),
     'inactive service cannot leak to response');
echo "OpenRoad bounded SQL engine MariaDB fixtures: ALL CHECKS PASSED\n";
