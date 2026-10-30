<?php
declare(strict_types=1);
if(!defined('OPENROAD_TRAIN_LIVE_TEST'))require_once __DIR__.'/rail_gateway.php';
/** Live data is only available in a short window around departure. */
function or_train_match_live(array $services,string $crs,string $to,int $epoch,string $headsign=''):array {
    $std=(new DateTimeImmutable('@'.$epoch))->setTimezone(new DateTimeZone('Europe/London'))->format('H:i');
    $matches=array_values(array_filter($services,static fn($s)=>
        is_array($s)&&preg_match('/^\d{1,2}:\d\d$/D',(string)($s['std']??'')) &&
        date('H:i',strtotime((string)$s['std']))===$std
    ));
    $normalise=static fn($x)=>preg_replace('/[^a-z0-9]/','',strtolower((string)$x));
    if(count($matches)>1&&$headsign!==''){
        $aim=$normalise($headsign);
        $subset=array_values(array_filter($matches,static fn($x)=>$normalise($x['destination']??'')===$aim));
        if(count($subset)===1)$matches=$subset;
    }
    if(count($matches)!==1){
        return ['status'=>count($matches)===0?'not_listed':'ambiguous',
                'message'=>count($matches)===0?'This train is not on the current live board. Scheduled times remain visible.'
                    :'Several trains have this departure time; platform and delay cannot be matched safely.',
                'matched'=>false];
    }
    $s=$matches[0];
    $etd=trim((string)($s['etd']??''));
    $cancelled=($s['cancelled']??false)===true;
    $prediction=null;
    if(preg_match('/^\d{1,2}:\d{2}$/D',$etd)){
        [$h,$m]=array_map('intval',explode(':',$etd));
        if($h<24&&$m<60)$prediction=sprintf('%02d:%02d',$h,$m);
    }
    if(strcasecmp($etd,'On time')===0)$prediction=$std;
    $delayMinutes=null;
    if($prediction!==null && !$cancelled){
        [$h,$m]=array_map('intval',explode(':',$std));
        [$eh,$em]=array_map('intval',explode(':',$prediction));
        $delta=($eh*60+$em)-($h*60+$m);
        if($delta < -720)$delta+=1440;
        if($delta > 720)$delta-=1440;
        if($delta>=0&&$delta<=360)$delayMinutes=$delta;
    }
    return ['status'=>'matched','matched'=>true,
        'station'=>$crs,'toCrs'=>$to,'scheduled'=>$std,
        'expected'=>$cancelled?'Cancelled':($prediction??($etd?:'Not available')),
        'platform'=>substr((string)($s['platform']??''),0,16),
        'delayMinutes'=>$delayMinutes,'cancelled'=>$cancelled,
        'destination'=>substr((string)($s['destination']??''),0,100),
        'serviceID'=>substr((string)($s['serviceID']??''),0,128),
        'operator'=>substr((string)($s['operator']??''),0,90),
        'message'=>$cancelled?'Service cancelled':($delayMinutes!==null&&$delayMinutes>0?'Delayed by '.$delayMinutes.' minutes':'Live service matched')];
}
function or_train_live_lookup(string $from,string $to,int $epoch,string $headsign='',
                              ?callable $board=null,?int $now=null):array {
    $now=$now??time();
    if(!preg_match('/^[A-Z]{3}$/D',$from)||!preg_match('/^[A-Z]{3}$/D',$to) ||
       abs($epoch-$now)>5*86400)throw new InvalidArgumentException('Invalid train request');
    $offset=(int)floor(($epoch-$now)/60);
    if($offset>200)return ['status'=>'not_yet','matched'=>false,
                          'message'=>'Live platforms and delays are usually unavailable this far ahead. Showing the scheduled timetable.'];
    if($offset < -100)return ['status'=>'expired','matched'=>false,
                          'message'=>'This train has already departed the live-board window.'];
    // Query the planned window rather than whatever eight trains happen
    // to leave immediately. One bounded provider call with existing hourly quota.
    $boardOffset=max(-119,min(119,$offset-25));
    [$status,$result]=($board??'openroad_rail_board')($from,null,null,null,null,$boardOffset,32);
    if($status!==200||!is_array($result))return ['status'=>'unavailable','matched'=>false,
                            'message'=>'Live train information is temporarily unavailable'];
    $match=or_train_match_live((array)($result['services']??[]),$from,$to,$epoch,$headsign);
    $match['checkedAt']=(string)($result['checkedAt']??gmdate('c',$now));
    return $match;
}
