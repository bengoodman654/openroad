<?php
// Private, signed multimodal bus ↔ train ↔ bus planner.
// Route searches only read indexed timetables; never parse feeds or contact providers.
@ini_set('memory_limit','96M');
@set_time_limit(13);
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||!is_file($private.'/lib/router.php')||
   !is_file($private.'/lib/multimodal_planner.php')){http_response_code(404);exit;}
require_once $private.'/lib/router.php';
require_once $private.'/lib/auth.php';
require_once $private.'/lib/multimodal_planner.php';
try{
    $body=openroad_require_post_json();
    $db=openroad_db();
    openroad_require_signed($db,$body);
    $data=json_decode($body,true);
    if(!is_array($data))openroad_json(['ok'=>false,'error'=>'Invalid request'],400);
    $from=$data['from']??null;$to=$data['to']??null;
    if(!is_array($from)||!is_array($to))openroad_json(['ok'=>false,'error'=>'Invalid location'],400);
    foreach([$from,$to] as $p){
        if(!isset($p['lat'],$p['lon'])||!is_numeric($p['lat'])||!is_numeric($p['lon'])||
           !is_finite((float)$p['lat'])||!is_finite((float)$p['lon'])||
           abs((float)$p['lat'])>90||abs((float)$p['lon'])>180)
            openroad_json(['ok'=>false,'error'=>'Invalid location'],400);
    }
    $in=is_array($data['settings']??null)?$data['settings']:[];
    $settings=[
        'walkSpeed'=>in_array($in['walkSpeed']??null,['slow','normal','fast'],true)?$in['walkSpeed']:'normal',
        'transferBuffer'=>($in['transferBuffer']??null)==='cautious'?'cautious':'normal',
        'maxWalkMeters'=>max(300,min(2500,(int)($in['maxWalkMeters']??1600))),
    ];
    // A slow feeder DB lookup must not monopolise shared MySQL resources.
    try{$db->exec('SET SESSION max_statement_time=0.85');}
    catch(Throwable $ignored){try{$db->exec('SET SESSION max_execution_time=850');}catch(Throwable $ignored2){}}
    $result=or_mm_plan($db,(float)$from['lat'],(float)$from['lon'],
              (float)$to['lat'],(float)$to['lon'],$settings);
    if(empty($result['routes']))openroad_json(['ok'=>false,'error'=>'No timetable-verified bus and train connection was found'],422);
    openroad_json($result+['ok'=>true],200);
}catch(RuntimeException $e){
    // Dates/coverage may expire; do not display stale journeys as valid.
    openroad_json(['ok'=>false,'error'=>'Multimodal timetable unavailable or incomplete'],503);
}catch(Throwable $e){
    openroad_json(['ok'=>false,'error'=>'Multimodal planning is unavailable'],503);
}
