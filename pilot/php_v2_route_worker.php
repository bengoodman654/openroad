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
        if($check()){
            $state=$registry->finish($ticket,$principal,(int)$clock());
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        }
        $state=$registry->finish($ticket,$principal,(int)$clock());
        if($state!=='COMPLETED')
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        return ['outcome'=>'OK','remoteJobStatus'=>'COMPLETED',
                'results'=>$result,'researchOnly'=>true];
    } catch(Throwable $e){
        $state=$registry->finish($ticket,$principal,(int)$clock());
        if($check() || $e->getMessage()==='REQUEST_CANCELLED'){
            return ['outcome'=>'CANCELLED','remoteJobStatus'=>$state,
                    'results'=>[],'researchOnly'=>true];
        }
        // No internal exception text is returned to a caller.
        return ['outcome'=>'PROVIDER_UNAVAILABLE','remoteJobStatus'=>$state,
                'results'=>[],'researchOnly'=>true];
    }
}
