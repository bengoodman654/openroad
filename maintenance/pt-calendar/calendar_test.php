<?php
declare(strict_types=1);
require_once __DIR__.'/calendar_extension.php';
function ok(bool $v,string $description):void{
    if(!$v)throw new RuntimeException("FAIL ".$description);
    echo "PASS ".$description."\n";
}
function throws(callable $fn,string $label):void{
    try{$fn();}catch(Throwable $e){ok(true,$label);return;}
    throw new RuntimeException("Expected rejection: ".$label);
}
$td=sys_get_temp_dir().'/or-calendar-'.bin2hex(random_bytes(6));mkdir($td,0700);
try {
    $path=$td.'/feed.zip';$z=new ZipArchive();
    if($z->open($path,ZipArchive::CREATE)!==true)throw new RuntimeException('Could not make ZIP');
    $z->addFromString('calendar.txt',
       "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n".
       "MON_FRI,1,1,1,1,1,0,0,20261001,20270228\n".
       "ONCE,0,0,0,0,0,0,0,20261001,20270228\n".
       "ORPHAN,1,1,1,1,1,1,1,20261001,20270228\n");
    $z->addFromString('calendar_dates.txt',
       "service_id,date,exception_type\n".
       "MON_FRI,20261112,2\n".
       "ONCE,20261114,1\n".
       "ORPHAN,20261114,1\n");
    $z->close();
    $z=new ZipArchive();$z->open($path);
    $rows=or_calendar_expand($z,['MON_FRI'=>true,'ONCE'=>true],
                             '2026-11-10','2026-11-16');$z->close();
    $key=array_fill_keys(array_map(static fn($r)=>implode(':',$r),$rows),true);
    ok(isset($key['MON_FRI:2026-11-10']), 'weekday service included');
    ok(!isset($key['MON_FRI:2026-11-12']), 'service exception removal');
    ok(!isset($key['MON_FRI:2026-11-14']), 'Saturday weekly exclusion');
    ok(isset($key['ONCE:2026-11-14']), 'exception-only service included');
    ok(!isset($key['ORPHAN:2026-11-14']), 'do not create calendar entries for nonexistent trip service');
    throws(fn()=>or_calendar_days('2026-10-01','2027-01-15'),
           'oversized refresh horizon rejected');
    $db=new PDO('mysql:host=127.0.0.1;port=3306;dbname=calendar_fixture;charset=utf8mb4',
        'calendar_test','ci-only-password',
        [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
         PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $schema=file_get_contents($argv[1]??'');
    if(!$schema)throw new RuntimeException('Schema path not supplied');
    foreach(preg_split('/;\s*(?:\r?\n|$)/',$schema) as $statement)
        if(trim($statement)!=='')$db->exec($statement);
    $db->exec("INSERT INTO or_regions VALUES('south_west',211,'Synthetic',NOW(),NOW(),1)");
    $db->exec("INSERT INTO or_routes(dataset_id,route_id) VALUES(211,'R')");
    $db->exec("INSERT INTO or_trips(dataset_id,trip_id,route_id,service_id) VALUES(211,'T1','R','MON_FRI'),(211,'T2','R','ONCE')");
    $db->exec("INSERT INTO or_service_dates VALUES(211,'MON_FRI','2026-11-09')");
    $db->exec("UPDATE or_regions SET updated_at='2026-01-01' WHERE region_key='south_west'");
    throws(fn()=>or_calendar_plan($db,'south_west',$path,
                                 new DateTimeImmutable('2026-10-28'),45),
           'cached feed must match active dataset generation');
    $db->exec("UPDATE or_regions SET updated_at=NOW() WHERE region_key='south_west'");
    $plan=or_calendar_plan($db,'south_west',$path,
                          new DateTimeImmutable('2026-10-28'),45);
    ok($plan['outcome']==='EXTEND','plan extends 9 Nov to 12 Dec');
    ok($plan['newLast']==='2026-12-12','horizon deterministic');
    $count=or_calendar_apply($db,$plan);
    ok($count===count($plan['rows'])&&$count>10,'bounded calendar rows inserted');
    ok((int)$db->query("SELECT COUNT(*) FROM or_trips")->fetchColumn()===2,
       'trip table unchanged');
    ok((int)$db->query("SELECT COUNT(*) FROM or_stop_times")->fetchColumn()===0,
       'stop-time table untouched');
    $again=or_calendar_plan($db,'south_west',$path,
                           new DateTimeImmutable('2026-10-28'),45);
    ok($again['outcome']==='CURRENT','calendar extension is idempotent');
    ok((int)$db->query("SELECT COUNT(*) FROM or_service_dates WHERE service_id='ORPHAN'")->fetchColumn()===0,
       'unreferenced service never inserted');
    echo "OpenRoad calendar-only GTFS maintenance: ALL CHECKS PASSED\n";
} finally {foreach(glob($td.'/*')?:[] as $f)@unlink($f);@rmdir($td);}
