<?php
declare(strict_types=1);
/**
 * Private signed-worker research adapter for source-pinned GTFS city planner.
 * Never call directly from a public route. Requires the existing v2 HMAC
 * task registry and already-authenticated device-owned ticket.
 */
function ptv2_run_city_process(array $canonicalQuery, callable $cancelCheck,
                                array $source, int $deadlineSeconds=11): array {
    $python=$source['python']??'';
    $script=$source['script']??'';
    $index=$source['index']??'';
    $cache=$source['snapshotCache']??null;
    $packageSha=$source['packageSha256']??null;
    $useCache=is_string($cache)&&$cache!=='';
    $region=$source['region']??'';
    $sha=$source['sourceSha256']??'';
    if(!is_string($python)||!is_string($script)||!is_string($index)||
       !is_string($region)||!is_string($sha)||
       !in_array($region,['south_west','west_midlands'],true)||
       !preg_match('/^[a-f0-9]{64}$/D',$sha)||
       !is_file($python)||!is_executable($python)||
       !is_file($script)||is_link($script)||
       ($useCache?
           (!is_file($cache)||is_link($cache)||
            !is_string($packageSha)||
            !preg_match('/^[a-f0-9]{64}$/D',$packageSha)):
           (!is_file($index)||is_link($index)))||
       $deadlineSeconds<2||$deadlineSeconds>14)
        throw new RuntimeException('UNPREPARED_CITY_SOURCE');
    if($cancelCheck())throw new RuntimeException('REQUEST_CANCELLED');
    $settings=$canonicalQuery['settings']??[];
    $walkMinutes=$settings['maxWalk']??10;
    $speeds=['slow'=>0.9,'normal'=>1.25,'fast'=>1.6];
    $speed=$speeds[$settings['walkSpeed']??'normal']??null;
    if(!is_int($walkMinutes)||$walkMinutes<3||$walkMinutes>60||$speed===null)
        throw new InvalidArgumentException('Invalid walking preference');
    $requestedWalkMetres=(int)ceil($walkMinutes*60*$speed);
    // Research scope cannot silently broaden OR narrow the phone setting.
    if($requestedWalkMetres>1800)
        throw new RuntimeException('RESEARCH_WALKING_LIMIT_UNSUPPORTED');
    $date=$source['serviceDate']??null;
    $clock=$source['earliestSec']??null;
    if(!is_string($date)||!preg_match('/^\d{4}-\d{2}-\d{2}$/D',$date)||
       !is_int($clock)||$clock<0||$clock>172800)
        throw new RuntimeException('INVALID_SOURCE_CLOCK');
    $payload=[
        'from'=>$canonicalQuery['from']??null,
        'to'=>$canonicalQuery['to']??null,
        'serviceDate'=>$date,'earliestSec'=>$clock,
        'maxWalkMetres'=>$requestedWalkMetres,
    ];
    $json=json_encode($payload,JSON_THROW_ON_ERROR);
    if(strlen($json)>4096)
        throw new InvalidArgumentException('Oversized worker request');
    $command=[$python,'-B',$script,
              '--region',$region,'--source-sha',$sha];
    if($useCache){
        array_push($command,'--snapshot-cache',$cache,
                   '--package-sha',$packageSha);
    }else{
        array_push($command,'--index',$index);
    }
    $pipes=[];
    $process=proc_open($command,
        [0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes,
        dirname($script),
        ['PYTHONDONTWRITEBYTECODE'=>'1']);
    if(!is_resource($process))
        throw new RuntimeException('UNAVAILABLE_WORKER_RUNTIME');
    $stdout='';$stderr='';$exited=null;$exitStatus=null;
    $started=microtime(true);
    try{
        fwrite($pipes[0],$json);
        fclose($pipes[0]);unset($pipes[0]);
        stream_set_blocking($pipes[1],false);
        stream_set_blocking($pipes[2],false);
        while(true){
            if($cancelCheck())
                throw new RuntimeException('REQUEST_CANCELLED');
            if(microtime(true)-$started>$deadlineSeconds)
                throw new RuntimeException('RESEARCH_WORKER_TIME_BUDGET');
            $stdout.=stream_get_contents($pipes[1],8192);
            $stderr.=stream_get_contents($pipes[2],2048);
            if(strlen($stdout)>131072||strlen($stderr)>8192)
                throw new RuntimeException('RESEARCH_WORKER_OUTPUT_LIMIT');
            $status=proc_get_status($process);
            if(!$status['running']){
                $exited=true;
                $exitStatus=(int)($status['exitcode']??-1);
                $stdout.=stream_get_contents($pipes[1],8192);
                $stderr.=stream_get_contents($pipes[2],2048);
                break;
            }
            usleep(25000);
        }
        if(strlen($stdout)>131072||strlen($stderr)>8192)
            throw new RuntimeException('RESEARCH_WORKER_OUTPUT_LIMIT');
        $code=proc_close($process);
        $process=null;
        if(($exitStatus!==0 && $code!==0)||!is_string($stdout)||$stdout==='')
            throw new RuntimeException('RESEARCH_WORKER_FAILED');
        $reply=json_decode(trim($stdout),true,16,JSON_THROW_ON_ERROR);
        if(!is_array($reply)||
           ($reply['researchOnly']??null)!==true||
           !is_array($reply['results']??null)||
           count($reply['results'])>3)
            throw new RuntimeException('UNTRUSTED_WORKER_OUTPUT');
        foreach($reply['results'] as $result){
            if(!is_array($result)||($result['selectable']??null)!==false||
               ($result['sourceArchiveSha256']??null)!==$sha)
                throw new RuntimeException('UNTRUSTED_SCHEDULED_ROUTE');
        }
        return $reply;
    } finally {
        foreach($pipes as $handle){
            if(is_resource($handle))fclose($handle);
        }
        if(is_resource($process)){
            // The child has no permission to launch descendants. Signal
            // and reap it before returning control to authenticated task.
            @proc_terminate($process,15);
            usleep(35000);
            $status=@proc_get_status($process);
            if(is_array($status)&&($status['running']??false))
                @proc_terminate($process,9);
            @proc_close($process);
        }
    }
}
