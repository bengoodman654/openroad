<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_route_worker.php';
function must(bool $pass,string $label):void {
    if(!$pass)throw new RuntimeException('FAILED '.$label);
    echo "PASS $label\n";
}
$dir=sys_get_temp_dir().'/or-ptv2-worker-'.bin2hex(random_bytes(8));
mkdir($dir,0700);
try{
    $registry=new OpenRoadV2ResearchCancellation($dir,str_repeat('W',32),2,20);
    $id=['deviceId'=>'da000000-0000-4000-8000-000000000001'];
    $clock=static fn()=>100;
    $ticket=$registry->issue($id['deviceId'],'session',1,'server-snapshot',100,40);
    $ok=ptv2_run_authenticated_task($registry,$id,$ticket,
        static function($check){if($check())throw new RuntimeException('unexpected cancel');
                                return [['scheduled'=>'sample']];},$clock);
    must($ok['outcome']==='OK'&&$ok['remoteJobStatus']==='COMPLETED',
         'completed worker acknowledged before itinerary publication');
    must(count($ok['results'])===1,'completed worker publishes one mock result');
    $t2=$registry->issue($id['deviceId'],'session',2,'server-snapshot',100,40);
    $cancelled=ptv2_run_authenticated_task($registry,$id,$t2,
        static function($check)use($registry,$t2,$id){
            $registry->cancel($t2,$id['deviceId'],101);
            // Simulate slow/blocking work that completes AFTER cancellation.
            return [['shouldNeverAppear'=>true]];
        },$clock);
    must($cancelled['outcome']==='CANCELLED'&&$cancelled['results']===[],
         'mid-task cancellation wins race over computed journey');
    must($cancelled['remoteJobStatus']==='STOPPED',
         'worker reports STOPPED only after acknowledgement');
    $t3=$registry->issue($id['deviceId'],'session',3,'server-snapshot',100,40);
    $registry->cancel($t3,$id['deviceId'],100);
    $ran=false;
    $result=ptv2_run_authenticated_task($registry,$id,$t3,
        static function($check)use(&$ran){$ran=true;return [];},$clock);
    must($result['outcome']==='CANCELLED'&&!$ran,
         'cancel-before-registration forbids any worker execution');
    $t4=$registry->issue($id['deviceId'],'session',4,'server-snapshot',100,40);
    $failure=ptv2_run_authenticated_task($registry,$id,$t4,
        static function($check){throw new RuntimeException('private exception');},
        $clock);
    must($failure['outcome']==='PROVIDER_UNAVAILABLE'&&$failure['results']===[],
         'internal worker fault not mistaken for no journeys');
    echo "V2 authenticated worker cancellation integration: ALL TESTS PASSED\n";
}finally{
    foreach(glob($dir.'/*')?:[] as $p)unlink($p);
    rmdir($dir);
}
