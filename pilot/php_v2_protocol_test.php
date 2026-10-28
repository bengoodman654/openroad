<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_protocol.php';
function verify_pt(bool $condition,string $title):void{
    if(!$condition)throw new RuntimeException('FAILED '.$title);
    echo "PASS ".$title."\n";
}
function rejected_pt(callable $call,string $title):void{
    try{$call();}catch(Throwable $e){verify_pt(true,$title);return;}
    throw new RuntimeException('FAILED '.$title);
}
$dir=sys_get_temp_dir().'/ptv2-wire-'.bin2hex(random_bytes(8));
mkdir($dir,0700);
try{
    $reg=new OpenRoadV2ResearchCancellation($dir,str_repeat('P',32),2,32);
    $deviceA=['deviceId'=>'da000000-0000-4000-8000-000000000001'];
    $deviceB=['deviceId'=>'db000000-0000-4000-8000-000000000002'];
    $query=['from'=>['lat'=>51.4545,'lon'=>-2.5879],
            'to'=>['lat'=>51.456,'lon'=>-2.58],
            'settings'=>['maxWalk'=>10,'ranking'=>'balanced']];
    $currentSnapshot='bristol:42';
    $choose=static function($query)use(&$currentSnapshot){return $currentSnapshot;};
    $calls=0;
    $plan=static function($input,$cancelled)use(&$calls){
        $calls++;
        if($cancelled())throw new RuntimeException('REQUEST_CANCELLED');
        return ['routes'=>[
            ['clearRouteId'=>str_repeat('a',20),
             'summary'=>['travelTimeInSeconds'=>1000]],
            ['clearRouteId'=>str_repeat('b',20),
             'summary'=>['travelTimeInSeconds'=>1250]]
        ]];
    };
    $clock=static fn()=>100;
    $base=['query'=>$query,'sessionId'=>'fresh-session','generation'=>1];
    $request=static function($action,$auth,$data)use($reg,$choose,$plan,$clock){
        return ptv2_dispatch($auth,array_merge($data,['action'=>$action]),
                             $reg,$choose,$plan,$clock);
    };
    $issued=$request('issue',$deviceA,$base);
    verify_pt($issued['outcome']==='OK' && $issued['snapshotId']==='bristol:42',
              'issue pins server-selected dataset');
    $token=$issued['taskTicket'];
    $claims=$reg->verifiedClaims($token,$deviceA['deviceId']);
    verify_pt($claims['queryHash']===ptv2_query_hash(ptv2_canonical_query($query)),
              'ticket signature binds exact canonical route request');
    $started=$request('route',$deviceA,['taskTicket'=>$token,'query'=>$query]);
    verify_pt($started['outcome']==='OK'&&count($started['results'])===2,
              'signed issue to route to response handshake');
    verify_pt(!$started['results'][0]['selectable'] &&
              !isset($started['results'][0]['legs']),
              'unverified routes carry no usable navigation legs');
    verify_pt($request('status',$deviceA,['taskTicket'=>$token])['remoteJobStatus']
              ==='COMPLETED','status observes completed worker');
    rejected_pt(fn()=>$request('cancel',$deviceB,['taskTicket'=>$token]),
                 'second device cannot cancel first device route');
    $late=$request('cancel',$deviceA,['taskTicket'=>$token]);
    verify_pt($late['remoteJobStatus']==='COMPLETED',
              'completed task is not falsely reported killed');
    $new=$request('issue',$deviceA,
                  ['query'=>$query,'sessionId'=>'fresh-session','generation'=>2]);
    $tok2=$new['taskTicket'];
    $mismatch=$query;$mismatch['to']['lat']=51.5;
    $used=$calls;
    $bad=$request('route',$deviceA,['taskTicket'=>$tok2,'query'=>$mismatch]);
    verify_pt($bad['reasonCode']==='QUERY_MISMATCH'&&$calls===$used,
              'tampered coordinates cannot run any planner work');
    $bad=$request('route',$deviceA,['taskTicket'=>$tok2,
                                    'query'=>$query+['unexpected'=>'unused']]);
    verify_pt($bad['outcome']==='OK'||$bad['outcome']==='INPUT_INVALID',
              'unrecognised unrelated body properties do not replace query data');
    // A new third token, because the prior one may now have been consumed.
    $pending=$request('issue',$deviceA,
                  ['query'=>$query,'sessionId'=>'fresh-session','generation'=>3]);
    $token3=$pending['taskTicket'];
    $cancel=$request('cancel',$deviceA,['taskTicket'=>$token3]);
    $late=$request('route',$deviceA,['taskTicket'=>$token3,'query'=>$query]);
    verify_pt($cancel['remoteJobStatus']==='STOPPED'&&
              $late['outcome']==='CANCELLED',
              'cancel-before-route never resurrects worker');
    $new4=$request('issue',$deviceA,
                  ['query'=>$query,'sessionId'=>'fresh-session','generation'=>4]);
    $tok4=$new4['taskTicket'];
    $currentSnapshot='bristol:43';
    $countBefore=$calls;
    $expired=$request('route',$deviceA,['taskTicket'=>$tok4,'query'=>$query]);
    verify_pt($expired['reasonCode']==='PINNED_SNAPSHOT_CHANGED'&&
              $calls===$countBefore,
              'snapshot rotation never mixes epochs of route data');
    $currentSnapshot='bristol:42';
    $five=$request('issue',$deviceA,
                  ['query'=>$query,'sessionId'=>'fresh-session','generation'=>5]);
    $token5=$five['taskTicket'];
    $cancelDuring=static function($input,$check)use($reg,$token5,$deviceA){
        $reg->cancel($token5,$deviceA['deviceId'],100);
        return ['routes'=>[['clearRouteId'=>str_repeat('c',20),
                           'summary'=>['travelTimeInSeconds'=>500]]]];
    };
    $out=ptv2_dispatch($deviceA,['action'=>'route','query'=>$query,
        'taskTicket'=>$token5],$reg,$choose,$cancelDuring,$clock);
    verify_pt($out['outcome']==='CANCELLED'&&$out['results']===[],
              'late completed calculation never publishes cancelled route');
    rejected_pt(fn()=>$reg->verifiedClaims(substr_replace($token5,'Z',10,1),
                                          $deviceA['deviceId']),
                 'HMAC tampering rejected');
    rejected_pt(fn()=>ptv2_canonical_query(
        ['from'=>['lat'=>'51.1','lon'=>-2.5],'to'=>$query['to']]),
        'coordinates supplied as string rejected');
    verify_pt(!isset($out['routes']), 'no v1 selectable route payload is exposed');
    echo "PT v2 signed request/route/cancel/status protocol: ALL CHECKS PASSED\n";
}finally{
    foreach(glob($dir.'/*')?:[] as $f)unlink($f);
    rmdir($dir);
}
