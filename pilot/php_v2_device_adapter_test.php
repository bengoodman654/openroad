<?php
declare(strict_types=1);
require_once __DIR__ . '/php_v2_device_adapter.php';

function assert_pt(bool $value, string $label): void {
    if (!$value) throw new RuntimeException('FAILED: '.$label);
    echo "PASS: $label\n";
}
function assert_pt_throws(callable $fn, string $label): void {
    try {$fn();} catch (Throwable $e) {
        assert_pt(true, $label);return;
    }
    throw new RuntimeException('FAILED: '.$label);
}
$tmp=sys_get_temp_dir().'/openroad-ptv2-device-'.bin2hex(random_bytes(8));
mkdir($tmp,0700);
try {
    $r=new OpenRoadV2ResearchCancellation($tmp,str_repeat('T',32));
    $a=['deviceId'=>'da000000-0000-4000-8000-000000000001'];
    $b=['deviceId'=>'db000000-0000-4000-8000-000000000002'];
    $req=['sessionId'=>'session-1','generation'=>3,
          'deviceId'=>$b['deviceId']];
    $issued=ptv2_issue_for_device($r,$a,$req,'verified-snapshot-A',100);
    $token=$issued['taskTicket'];
    assert_pt($issued['status']==='ISSUED_ONLY','ticket is not an admitted job');
    assert_pt($r->register($token,$a['deviceId'],100)==='RUNNING',
              'worker registration bound to verified device A');
    assert_pt_throws(fn()=>ptv2_cancel_for_device(
        $r,$b,['taskTicket'=>$token],101),
        'different signed device cannot cancel A');
    $cancel=ptv2_cancel_for_device($r,$a,['taskTicket'=>$token],101);
    assert_pt($cancel['remoteJobStatus']==='STOPPING',
              'A may cancel its own job');
    assert_pt($r->shouldStop($token,$a['deviceId'],101),
              'worker acknowledges stop request cooperatively');
    assert_pt($r->finish($token,$a['deviceId'],102)==='STOPPED',
              'actual worker acknowledgement is separate');
    assert_pt_throws(fn()=>ptv2_issue_for_device(
        $r,[],['sessionId'=>'s','generation'=>4],'snapshot',100),
        'absent authenticated device refused');
    assert_pt_throws(fn()=>ptv2_issue_for_device(
        $r,$a,['sessionId'=>'s','generation'=>4],'',100),
        'server must pin a valid snapshot');
    assert_pt_throws(fn()=>ptv2_cancel_for_device(
        $r,$a,['taskTicket'=>''],100),
        'empty ticket cannot cancel');
    $next=ptv2_issue_for_device(
        $r,$a,['sessionId'=>'next','generation'=>4],
        'server-selected-snapshot',103);
    assert_pt($r->cancel($next['taskTicket'],$a['deviceId'],104)==='STOPPED',
              'cancel-before-worker registration creates tombstone');
    assert_pt($r->register($next['taskTicket'],$a['deviceId'],105)==='REJECTED_CANCELLED',
              'late worker can never start');
    echo "OpenRoad signed-device v2 adapter: ALL TESTS PASSED\n";
} finally {
    foreach(glob($tmp.'/*')?:[] as $file)unlink($file);
    rmdir($tmp);
}
