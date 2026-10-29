<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_device_adapter.php';

/**
 * Private research v2 worker adapter. NOT callable as a public endpoint.
 * $auth is the return value of openroad_require_signed(), never request JSON.
 * $work receives a cooperative stop-check closure. Blocking DB statements
 * may delay cancellation acknowledgement; STOPPING remains accurate.
 */
function ptv2_run_authenticated_task(
    OpenRoadV2ResearchCancellation $registry,
    array $auth, string $ticket, callable $work, callable $clock
): array {
    $principal=ptv2_authenticated_device($auth);
    $begin=$registry->register($ticket,$principal,(int)$clock());
    if($begin!=='RUNNING'){
        return ['outcome'=>$begin==='REJECTED_CANCELLED'?'CANCELLED':'RATE_LIMITED',
                'remoteJobStatus'=>$begin, 'results'=>[],
                'researchOnly'=>true];
    }
    $check=static function() use($registry,$ticket,$principal,$clock):bool {
        return $registry->shouldStop($ticket,$principal,(int)$clock());
    };
    try{
        if($check())throw new RuntimeException('REQUEST_CANCELLED');
        $result=$work($check);
        // Legacy planner returns a simple routes list. The newer
        // source-pinned city planner returns a typed outcome envelope.
        $isEnvelope=is_array($result)&&isset($result['outcome']);
        if($isEnvelope){
            $allowed=['OK','NO_JOURNEY','COVERAGE_MISSING',
                      'CALENDAR_MISSING','SEARCH_LIMIT',
                      'INPUT_INVALID','PROVIDER_UNAVAILABLE','CANCELLED'];
            if(!in_array($result['outcome'],$allowed,true)||
               !is_array($result['results']??null)||
               ($result['researchOnly']??false)!==true)
                throw new RuntimeException('INVALID_RESEARCH_OUTCOME');
            if($result['outcome']==='CANCELLED')
                throw new RuntimeException('REQUEST_CANCELLED');
        }
        if($check()){
            $state=$registry->finish($ticket,$principal,(int)$clock());
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        }
        $state=$registry->finish($ticket,$principal,(int)$clock());
        if($state!=='COMPLETED')
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        return ['outcome'=>$isEnvelope?$result['outcome']:'OK',
                'remoteJobStatus'=>'COMPLETED',
                'results'=>$isEnvelope?$result['results']:$result,
                'researchOnly'=>true];
    } catch(Throwable $e){
        // Evaluate cancellation BEFORE marking worker completed. A finished
        // job is not RUNNING, so checking afterwards would misclassify
        // ordinary provider failures as user cancellation.
        $wasCancelled=$check() || $e->getMessage()==='REQUEST_CANCELLED';
        $state=$registry->finish($ticket,$principal,(int)$clock());
        if($wasCancelled || $state==='STOPPED'){
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        }
        // No internal exception text is returned to a caller.
        return ['outcome'=>'PROVIDER_UNAVAILABLE','remoteJobStatus'=>$state,
                'results'=>[],'researchOnly'=>true];
    }
}
