<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_cancellation.php';
function must_process(bool $value,string $name):void {
    if(!$value)throw new RuntimeException('FAILED: '.$name);
    echo "PASS: $name\n";
}
function spawn_process(string $dir,string $key,string $ticket,
                       string $principal,string $name,int $delay=0):array {
    $flag=$dir.'/'.$name.'.started';
    $output=$dir.'/'.$name.'.json';
    $command=[PHP_BINARY,__DIR__.'/php_v2_process_worker.php',
              $dir,$key,$ticket,$principal,$flag,$output,(string)$delay];
    $spec=[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']];
    $pipes=[];
    $proc=proc_open($command,$spec,$pipes);
    if(!is_resource($proc))throw new RuntimeException('Could not start child PHP');
    fclose($pipes[0]);
    return [$proc,$pipes,$flag,$output];
}
function join_process(array $task):array {
    [$proc,$pipes,$flag,$output]=$task;
    $stdout=stream_get_contents($pipes[1]);fclose($pipes[1]);
    $stderr=stream_get_contents($pipes[2]);fclose($pipes[2]);
    $status=proc_close($proc);
    if($status!==0)throw new RuntimeException('Worker exit '.$status.' '.$stderr.' '.$stdout);
    $json=is_file($output)?json_decode(file_get_contents($output),true):null;
    if(!is_array($json))throw new RuntimeException('Missing worker reply');
    return $json;
}
function await_flag(string $path,int $ms=3000):bool {
    $deadline=microtime(true)+$ms/1000;
    while(microtime(true)<$deadline){
        if(is_file($path))return true;
        usleep(10000);
    }
    return false;
}
$dir=sys_get_temp_dir().'/ptv2-multiprocess-'.bin2hex(random_bytes(8));
mkdir($dir,0700);
$key=str_repeat('Q',32);
$a='da000000-0000-4000-8000-000000000001';
$b='db000000-0000-4000-8000-000000000002';
$reg=new OpenRoadV2ResearchCancellation($dir,$key,2,20);
try{
    $now=time();
    $aTicket=$reg->issue($a,'sessionA',1,'bristol:1',$now,15);
    $bTicket=$reg->issue($b,'sessionB',1,'bristol:1',$now,15);
    $workerA=spawn_process($dir,$key,$aTicket,$a,'A');
    $workerB=spawn_process($dir,$key,$bTicket,$b,'B');
    must_process(await_flag($workerA[2]),'device A work registered in separate PHP');
    must_process(await_flag($workerB[2]),'device B work registered concurrently');
    $cancelled=$reg->cancel($aTicket,$a,time());
    must_process($cancelled==='STOPPING','cancellation reaches running worker via shared lock');
    $answerA=join_process($workerA);
    $answerB=join_process($workerB);
    must_process($answerA['outcome']==='CANCELLED' && $answerA['results']===[],
                'cancelled process drops computed results');
    must_process($answerA['remoteJobStatus']==='STOPPED',
                'separate worker reports termination acknowledgement');
    must_process($answerB['outcome']==='OK' &&
                $answerB['remoteJobStatus']==='COMPLETED',
                'unrelated concurrent device survives cancellation');

    $lateTicket=$reg->issue($a,'sessionA',2,'bristol:1',time(),15);
    $lateWorker=spawn_process($dir,$key,$lateTicket,$a,'C',200);
    must_process($reg->cancel($lateTicket,$a,time())==='STOPPED',
                 'cancel before worker process has registered');
    $lateResult=join_process($lateWorker);
    must_process($lateResult['outcome']==='CANCELLED',
                 'late worker cannot resurrect cancelled ticket');
    must_process(!is_file($lateWorker[2]),
                 'cancel-before-registration does not run planner callback');
    echo "PT v2 independent-process cancellation: ALL CHECKS PASSED\n";
}finally {
    foreach(glob($dir.'/*')?:[] as $file)unlink($file);
    rmdir($dir);
}
