<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_route_worker.php';

/**
 * Versioned v2 handshake. NO HTTP I/O here; staged endpoint supplies:
 * - auth: result of the existing signed-device validator
 * - snapshotSelector: pure lookup of an already-prepared compatible dataset
 * - planner: bounded route calculation, with cancellation check
 * - clock: server clock
 *
 * Every response is research-only and never contains selectable navigation.
 */
function ptv2_canonical_query($input): array {
    if(!is_array($input))throw new InvalidArgumentException('Missing route query');
    if(array_diff(array_keys($input),['from','to','settings']))
        throw new InvalidArgumentException('Unexpected route fields');
    foreach(['from','to'] as $point){
        if(!is_array($input[$point]??null))
            throw new InvalidArgumentException('Missing route endpoint');
        if(array_diff(array_keys($input[$point]),['lat','lon']))
            throw new InvalidArgumentException('Unexpected coordinate fields');
    }
    $coords=[];
    foreach(['from','to'] as $point){
        $coordinates=[];
        foreach(['lat','lon'] as $axis){
            $raw=$input[$point][$axis]??null;
            if(!is_int($raw)&&!is_float($raw))
                throw new InvalidArgumentException('Route coordinates must be numeric');
            $value=(float)$raw;
            if(!is_finite($value)||
               abs($value)>($axis==='lat'?90:180))
                throw new InvalidArgumentException('Invalid route coordinates');
            $coordinates[$axis]=round($value,6);
        }
        $coords[$point]=$coordinates;
    }
    $s=$input['settings']??[];
    if(!is_array($s))throw new InvalidArgumentException('Invalid settings');
    $allowed=['maxWalk','walkSpeed','transferBuffer','ranking','phase'];
    if(array_diff(array_keys($s),$allowed))
        throw new InvalidArgumentException('Unexpected route setting');
    $max=$s['maxWalk']??10;
    if(!is_int($max)||$max<3||$max>60)
        throw new InvalidArgumentException('Invalid walking limit');
    foreach([
        'walkSpeed'=>['slow','normal','fast'],
        'transferBuffer'=>['normal','cautious'],
        'ranking'=>['quickest','balanced','changes'],
        'phase'=>['fast','full'],
    ] as $name=>$options){
        if(isset($s[$name])&&!in_array($s[$name],$options,true))
            throw new InvalidArgumentException('Invalid route option');
    }
    return [
        'from'=>$coords['from'], 'to'=>$coords['to'],
        'settings'=>[
            'maxWalk'=>$max, 'walkSpeed'=>$s['walkSpeed']??'normal',
            'transferBuffer'=>$s['transferBuffer']??'normal',
            'ranking'=>$s['ranking']??'balanced',
            'resultLimit'=>3,
            'phase'=>$s['phase']??'fast',
        ],
    ];
}
function ptv2_query_hash(array $query): string {
    return hash('sha256',json_encode($query,JSON_THROW_ON_ERROR|JSON_PRESERVE_ZERO_FRACTION));
}
function ptv2_snapshot_id($value): string {
    if(!is_string($value)||!preg_match('/^[A-Za-z0-9_:.-]{1,128}$/D',$value))
        throw new RuntimeException('No compatible verified snapshot');
    return $value;
}

/** Abstract response adapter; no map instructions or route geometry can leak. */
function ptv2_research_routes($raw): array {
    if(!is_array($raw)||!is_array($raw['routes']??null))
        throw new RuntimeException('Invalid route planner output');
    $out=[];
    foreach(array_slice($raw['routes'],0,3) as $route){
        if(!is_array($route)||!is_string($route['clearRouteId']??null)||
           !preg_match('/^[a-f0-9]{20}$/D',$route['clearRouteId'])||
           !is_array($route['summary']??null))
            throw new RuntimeException('Invalid scheduled route identity');
        $id='legacy-'.$route['clearRouteId'];
        if(isset($out[$id]))continue;
        $out[$id]=[
            'id'=>$id, 'selectable'=>false,
            'selectionBlocker'=>'UNVERIFIED_PEDESTRIAN_STOP_ACCESS',
            'travelTimeSeconds'=>(int)($route['summary']['travelTimeInSeconds']??0),
            'scheduledOnly'=>true,
        ];
    }
    return array_values($out);
}

/**
 * Adapt the source-pinned Python city planner into a NON-NAVIGABLE signed
 * response. No map geometry, boarding instructions or accessibility claim
 * may enter the existing Android guidance path at this stage.
 */
function ptv2_city_research_output($raw):array{
    if(!is_array($raw)||($raw['researchOnly']??null)!==true||
       !is_array($raw['results']??null)||count($raw['results'])>3)
        throw new RuntimeException('Invalid city research output');
    $outcome=$raw['outcome']??null;
    if(!in_array($outcome,['OK','NO_JOURNEY','COVERAGE_MISSING',
                            'CALENDAR_MISSING','SEARCH_LIMIT',
                            'INPUT_INVALID','PROVIDER_UNAVAILABLE',
                            'CANCELLED'],true))
        throw new RuntimeException('Unknown city research status');
    if($outcome!=='OK'&&count($raw['results'])!==0)
        throw new RuntimeException('Failed city search cannot contain routes');
    $out=[];
    foreach($raw['results'] as $route){
        if(!is_array($route)||($route['researchOnly']??false)!==true||
           ($route['selectable']??null)!==false||
           !is_string($route['clearRouteId']??null)||
           !preg_match('/^[0-9a-f]{20}$/D',$route['clearRouteId'])||
           !is_string($route['sourceArchiveSha256']??null)||
           !preg_match('/^[0-9a-f]{64}$/D',$route['sourceArchiveSha256'])||
           !is_array($route['busLegs']??null)||
           count($route['busLegs'])<1||count($route['busLegs'])>3||
           !is_int($route['departureSec']??null)||
           !is_int($route['arrivalLowerBoundSec']??null)||
           $route['arrivalLowerBoundSec']<$route['departureSec']||
           !is_int($route['changes']??null)||$route['changes']<0||
           $route['changes']>2)
            throw new RuntimeException('Invalid source-pinned itinerary');
        if(is_string($raw['snapshotId']??null) &&
           !hash_equals($raw['snapshotId'],$route['sourceArchiveSha256']))
            throw new RuntimeException('Itinerary source snapshot mismatch');
        $id='scheduled-'.$route['clearRouteId'];
        if(isset($out[$id]))continue;
        $out[$id]=[
            'id'=>$id,'selectable'=>false,
            'selectionBlocker'=>'UNVERIFIED_ENDPOINT_PEDESTRIAN_ACCESS',
            'travelTimeSeconds'=>$route['arrivalLowerBoundSec']-
                                 $route['departureSec'],
            'changes'=>$route['changes'],
            'scheduledOnly'=>true,
            'researchOnly'=>true,
        ];
    }
    return ['outcome'=>$outcome,'results'=>array_values($out),
            'researchOnly'=>true];
}

/**
 * All actions are authenticated by signed request at the HTTP boundary.
 * Query and snapshot must match the server-issued signed ticket exactly.
 */
function ptv2_dispatch(array $auth,array $input,
    OpenRoadV2ResearchCancellation $registry,
    callable $snapshotSelector,callable $planner,callable $clock):array {
    $device=ptv2_authenticated_device($auth);
    $action=$input['action']??null;
    if(!in_array($action,['issue','route','cancel','status'],true))
        return ['outcome'=>'INPUT_INVALID','reasonCode'=>'INVALID_OPERATION',
                'researchOnly'=>true];
    $now=(int)$clock();
    if($action==='issue'){
        $query=ptv2_canonical_query($input['query']??null);
        $snapshot=ptv2_snapshot_id($snapshotSelector($query));
        $request=[
            'sessionId'=>$input['sessionId']??null,
            'generation'=>$input['generation']??null,
        ];
        $issued=ptv2_issue_for_device($registry,$auth,$request,$snapshot,
                                      $now,ptv2_query_hash($query));
        return ['outcome'=>'OK','taskType'=>'JOURNEY',
                'snapshotId'=>$snapshot,'generation'=>$request['generation'],
                'taskTicket'=>$issued['taskTicket'],
                'remoteJobStatus'=>'ISSUED_ONLY','researchOnly'=>true];
    }
    $token=$input['taskTicket']??null;
    if(!is_string($token)||!strlen($token)||strlen($token)>1024)
        return ['outcome'=>'INPUT_INVALID','reasonCode'=>'MISSING_TICKET',
                'researchOnly'=>true];
    $claims=$registry->verifiedClaims($token,$device);
    $identity=['taskId'=>$claims['taskId'],
               'generation'=>$claims['generation'],
               'snapshotId'=>$claims['snapshotId']];
    if($action==='cancel'){
        return array_merge($identity,ptv2_cancel_for_device(
            $registry,$auth,['taskTicket'=>$token],$now));
    }
    if($action==='status'){
        return array_merge($identity,[
            'outcome'=>'OK',
            'remoteJobStatus'=>$registry->status($token,$device,$now),
            'researchOnly'=>true]);
    }
    // Never let a valid ticket be reused against different coordinates,
    // options, region or dataset version.
    if(!is_string($claims['queryHash']??null))
        return array_merge($identity,[
            'outcome'=>'INPUT_INVALID','reasonCode'=>'UNBOUND_TICKET',
            'researchOnly'=>true,'results'=>[]]);
    $query=ptv2_canonical_query($input['query']??null);
    if(!hash_equals($claims['queryHash'],ptv2_query_hash($query)))
        return array_merge($identity,[
            'outcome'=>'INPUT_INVALID','reasonCode'=>'QUERY_MISMATCH',
            'researchOnly'=>true,'results'=>[]]);
    $snapshot=ptv2_snapshot_id($snapshotSelector($query));
    if($snapshot!==$claims['snapshotId'])
        return array_merge($identity,[
            'outcome'=>'COVERAGE_MISSING',
            'reasonCode'=>'PINNED_SNAPSHOT_CHANGED',
            'researchOnly'=>true,'results'=>[]]);
    $worked=ptv2_run_authenticated_task($registry,$auth,$token,
        static function($check)use($planner,$query) {
            $raw=$planner($query,$check);
            if(is_array($raw)&&isset($raw['outcome'])&&
               array_key_exists('results',$raw))
                return ptv2_city_research_output($raw);
            return ptv2_research_routes($raw);
        },$clock);
    return array_merge($identity,$worked);
}
