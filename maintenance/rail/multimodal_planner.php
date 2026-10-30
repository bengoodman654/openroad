<?php
declare(strict_types=1);
/**
 * OpenRoad: timetable-coherent bus → train(s) → bus/foot itinerary composer.
 * No live API calls, no downloads, no writes or timetable imports in requests.
 * The existing regional bus router is included but not modified.
 */
require_once __DIR__.'/rail_planner.php';

function or_mm_walk_seconds(float $metres,float $speed=1.25):int {
    return (int)ceil($metres*1.25/max(0.8,min(1.8,$speed)));
}
function or_mm_stations(array $stations,float $lat,float $lon,int $limit=4,float $max=12000.0):array {
    $out=[];
    foreach($stations as $code=>$s){
        if(!preg_match('/^[A-Z]{3}$/D',(string)$code)||!is_array($s)||count($s)<3)continue;
        $metres=or_rail_km($lat,$lon,(float)$s[1],(float)$s[2])*1000;
        if($metres<=$max)$out[]=['station'=>(string)$code,'metres'=>$metres,
             'walk'=>or_mm_walk_seconds($metres),'lat'=>(float)$s[1],'lon'=>(float)$s[2]];
    }
    usort($out,static fn($x,$y)=>$x['metres']<=>$y['metres']);
    return array_slice($out,0,$limit);
}
function or_mm_epoch_day(int $time):string {
    return (new DateTimeImmutable('@'.$time))->setTimezone(new DateTimeZone('Europe/London'))->format('Y-m-d');
}
function or_mm_midnight(int $time):int {
    return (new DateTimeImmutable('@'.$time))->setTimezone(new DateTimeZone('Europe/London'))->setTime(0,0)->getTimestamp();
}
function or_mm_point(array $p):array {
    return ['latitude'=>(float)$p['lat'],'longitude'=>(float)$p['lon']];
}
function or_mm_walk_leg(array $a,array $b,string $nameA,string $nameB,int $start,int $seconds):array {
    $metres=or_rail_km((float)$a['lat'],(float)$a['lon'],(float)$b['lat'],(float)$b['lon'])*1000;
    return ['leg'=>['mode'=>'foot','from'=>$nameA,'to'=>$nameB,
       'fromLat'=>(float)$a['lat'],'fromLon'=>(float)$a['lon'],
       'toLat'=>(float)$b['lat'],'toLon'=>(float)$b['lon'],
       'departure'=>date('H:i',$start),'arrival'=>date('H:i',$start+$seconds),
       'departureEpoch'=>$start,'arrivalEpoch'=>$start+$seconds,
       'durationSeconds'=>$seconds,'distanceMetres'=>(int)ceil($metres),
       'timeStatus'=>'scheduled','dataSource'=>'Walking time estimate',
       'geometryStatus'=>'approximate'],
       'geometry'=>['points'=>[or_mm_point($a),or_mm_point($b)]]];
}
function or_mm_insert_walk(array &$legs,array &$geometry,array $a,array $b,string $from,string $to,int $start,int $seconds):void {
    if($seconds<20)return;
    $walk=or_mm_walk_leg($a,$b,$from,$to,$start,$seconds);
    $legs[]=$walk['leg'];$geometry[]=$walk['geometry'];
}
/**
 * One indexed, same-region, direct-bus-only feeder search. No transfer scans.
 * Exact scheduled departure and arrival epochs are used for all joins.
 * On SQL timeout or unsupported/unprepared region return null, not a fabricated bus.
 */
function or_mm_feeder(PDO $db,array $a,array $b,int $earliest,int $window=6000,
                       float $walkSpeed=1.25):?array {
    if($window<300||$window>10800)return null;
    if(or_mm_epoch_day($earliest)!==or_mm_epoch_day(time()))return null;
    if(!function_exists('or_dataset_for_points')||!function_exists('or_nearby_stops')||
       !function_exists('or_direct_candidates'))return null;
    try {
        // This lookup is intentionally bounded so a missing feeder cannot overload
        // websites and email hosted on the same cPanel account.
        [$ds,$region]=or_dataset_for_points($db,(float)$a['lat'],(float)$a['lon'],
                        (float)$b['lat'],(float)$b['lon']);
        $from=or_stop_map(or_nearby_stops($db,$ds,(float)$a['lat'],(float)$a['lon'],500,5));
        $to=or_stop_map(or_nearby_stops($db,$ds,(float)$b['lat'],(float)$b['lon'],650,7));
        if(!$from||!$to)return null;
        $midnight=or_mm_midnight($earliest);
        $since=$earliest-$midnight;
        if($since<0||$since>=86400)return null;
        $candidate=or_direct_candidates($db,$ds,$from,$to,(int)$since,min(7200,$window));
        $best=null;
        foreach(array_slice($candidate,0,450) as $row){
            $board=$from[$row['board_stop']]??null;$alight=$to[$row['alight_stop']]??null;
            if(!$board||!$alight)continue;
            $walkA=or_mm_walk_seconds((float)$board['distance'],$walkSpeed);
            $walkB=or_mm_walk_seconds((float)$alight['distance'],$walkSpeed);
            $departure=$midnight+(int)$row['depart_sec'];
            $arrival=$midnight+(int)$row['arrive_sec'];
            if($departure<$earliest+$walkA || $arrival<=$departure || $arrival+$walkB>$earliest+$window+3600)continue;
            $candidateScore=$arrival+$walkB;
            if($best!==null&&$candidateScore>=$best['arrival'])continue;
            $pa=['lat'=>(float)$board['stop_lat'],'lon'=>(float)$board['stop_lon']];
            $pb=['lat'=>(float)$alight['stop_lat'],'lon'=>(float)$alight['stop_lon']];
            $le=[];$geom=[];
            or_mm_insert_walk($le,$geom,$a,$pa,'Starting point',(string)$board['stop_name'],$earliest,$walkA);
            $line=trim((string)($row['short_name']?:$row['long_name']?:'Bus'));
            $leg=['mode'=>'bus','line'=>$line,'from'=>(string)$board['stop_name'],'to'=>(string)$alight['stop_name'],
                  'fromLat'=>$pa['lat'],'fromLon'=>$pa['lon'],'toLat'=>$pb['lat'],'toLon'=>$pb['lon'],
                  'fromAtco'=>(string)$row['board_stop'],'toAtco'=>(string)$row['alight_stop'],
                  'stopCount'=>max(1,(int)$row['alight_seq']-(int)$row['board_seq']),
                  'departureEpoch'=>$departure,'arrivalEpoch'=>$arrival,
                  'departure'=>date('H:i',$departure),'arrival'=>date('H:i',$arrival),
                  'durationSeconds'=>$arrival-$departure,'timeStatus'=>'scheduled',
                  'dataSource'=>'DfT BODS scheduled bus timetable','geometryStatus'=>'approximate',
                  'stops'=>[['lat'=>$pa['lat'],'lon'=>$pa['lon'],'name'=>$row['board_stop']],
                            ['lat'=>$pb['lat'],'lon'=>$pb['lon'],'name'=>$row['alight_stop']]]];
            $le[]=$leg;$geom[]=['points'=>[or_mm_point($pa),or_mm_point($pb)]];
            or_mm_insert_walk($le,$geom,$pb,$b,(string)$alight['stop_name'],'Station / destination',$arrival,$walkB);
            $best=['departure'=>$departure,'arrival'=>$arrival+$walkB,'legs'=>$le,'geometry'=>$geom,
                   'source'=>'scheduled-bus','walkSeconds'=>$walkA+$walkB];
        }
        return $best;
    }catch(Throwable $ignored){return null;}
}
function or_mm_rail_times(array $route):?array {
    $trains=array_values(array_filter($route['transitLegs']??[],
        static fn($l)=>($l['mode']??null)==='train'));
    if(!$trains)return null;
    $a=$trains[0];$b=$trains[count($trains)-1];
    if(!isset($a['departureEpoch'],$b['arrivalEpoch'],$a['fromCrs'],$b['toCrs']))return null;
    return ['from'=>(string)$a['fromCrs'],'to'=>(string)$b['toCrs'],
            'departure'=>(int)$a['departureEpoch'],'arrival'=>(int)$b['arrivalEpoch']];
}
/**
 * Merges aligned transitLegs/geometry only after checking both transfer buffers.
 * Rejecting a connection is safer than showing impossible travel directions.
 */
function or_mm_compose(array $rail,array $origin,array $destination,array $start,array $end,
                       int $now,int $buffer=300):?array {
    $times=or_mm_rail_times($rail);
    if($times===null)return null;
    if(($start['station']??null)!==$times['from']||($end['station']??null)!==$times['to'])return null;
    if((int)$start['arrival']+$buffer>$times['departure'])return null;
    if(($end['source']??'foot')==='scheduled-bus'&&$times['arrival']+180>(int)$end['departure'])return null;
    $railLegs=$rail['transitLegs']??[];$railGeom=$rail['legs']??[];
    if(count($railLegs)!==count($railGeom)||count($railLegs)<3)return null;
    $travelLegs=array_slice($railLegs,1,-1);$travelGeom=array_slice($railGeom,1,-1);
    $before=$start['legs']??[];$beforeGeom=$start['geometry']??[];
    $after=$end['legs']??[];$afterGeom=$end['geometry']??[];
    if(count($before)!==count($beforeGeom)||count($after)!==count($afterGeom))return null;
    $legs=[...$before,...$travelLegs,...$after];
    $geom=[...$beforeGeom,...$travelGeom,...$afterGeom];
    if(count($legs)!==count($geom))return null;
    $last=(int)$end['arrival'];
    if($last<$times['arrival']||$last>$now+12*3600)return null;
    $busCount=count(array_filter($legs,static fn($l)=>($l['mode']??null)==='bus'));
    if($busCount<1)return null;
    $rail['transitLegs']=$legs;$rail['legs']=$geom;
    $rail['summary']['travelTimeInSeconds']=$last-$now;
    $rail['clearRouteDeparture']=date('H:i',$now);
    $rail['clearRouteArrival']=date('H:i',$last);
    $rail['clearRouteDataStatus']='scheduled';
    $rail['clearRouteDataSource']='OpenRoad: DfT BODS + scheduled National Rail';
    $rail['clearRouteWarning']='Bus and train times are scheduled. Connections may be disrupted; check live departures before travelling.';
    $rail['clearRouteMultimodal']=true;
    $rail['clearRouteId']='mixed-'.substr(hash('sha256',
        implode('|',array_map(static fn($l)=>($l['mode']??'').':'.($l['departureEpoch']??0).':'.($l['fromAtco']??$l['fromCrs']??''),$legs))),0,24);
    $rail['guidance']=['instructions'=>[]];
    return $rail;
}
/**
 * $feeder is injectable for deterministic tests, never supplied by clients.
 * Request limits: max three outbound station access queries and at most three
 * final station feeders. Rail search itself uses a read-only SQLite index.
 */
function or_mm_plan(PDO $db,float $olat,float $olon,float $dlat,float $dlon,
                    array $settings=[],?callable $feeder=null,?int $now=null,?string $root=null):array {
    $now=$now??time();$root=$root??__DIR__.'/../cache/rail-routing/current';
    [$meta,$stations]=or_rail_index($root);
    $maxWalk=max(300,min(2500,(int)($settings['maxWalkMeters']??1600)));
    $walkSpeed=($settings['walkSpeed']??'normal')==='fast'?1.5:
               (($settings['walkSpeed']??'normal')==='slow'?1.0:1.25);
    $buffer=($settings['transferBuffer']??'normal')==='cautious'?540:300;
    $from=['lat'=>$olat,'lon'=>$olon];$to=['lat'=>$dlat,'lon'=>$dlon];
    $candidates=or_mm_stations($stations,$olat,$olon,4,10000);
    $targetCandidates=or_mm_stations($stations,$dlat,$dlon,4,10000);
    $lookup=$feeder??'or_mm_feeder';
    $starts=[];$startDetails=[];$busCalls=0;
    foreach($candidates as $s){
        $station=['lat'=>$s['lat'],'lon'=>$s['lon']];
        if($s['metres']<=$maxWalk){
            $sec=or_mm_walk_seconds($s['metres'],$walkSpeed);
            $start=['source'=>'foot','station'=>$s['station'],'arrival'=>$now+$sec,
                    'legs'=>[],'geometry'=>[]];
            or_mm_insert_walk($start['legs'],$start['geometry'],$from,$station,'Starting point',
                $stations[$s['station']][0],$now,$sec);
        }else{
            if(++$busCalls>3)continue;
            $start=$lookup($db,$from,$station,$now,7200,$walkSpeed);
            if($start===null)continue;
            $start['station']=$s['station'];
        }
        $ready=(int)$start['arrival']+$buffer;
        $starts[]=['station'=>$s['station'],'walk'=>0,'ready'=>$ready];
        $startDetails[$s['station']]=$start;
    }
    if(!$starts)return ['routes'=>[],'coverage'=>'no_station_access','clearRoutePlanner'=>'OpenRoad-multimodal'];
    $ends=[];$targetDetails=[];
    foreach($targetCandidates as $t){
        $walk=or_mm_walk_seconds($t['metres'],$walkSpeed);
        $needsBus=$t['metres']>$maxWalk;
        $ends[]=['station'=>$t['station'],'walk'=>$needsBus?900:$walk];
        $targetDetails[$t['station']]=['station'=>$t['station'],'needsBus'=>$needsBus,'walk'=>$walk];
    }
    if(!$ends)return ['routes'=>[],'coverage'=>'no_station_egress','clearRoutePlanner'=>'OpenRoad-multimodal'];
    $result=or_rail_plan($olat,$olon,$dlat,$dlon,$root,$now,
              ['starts'=>$starts,'ends'=>$ends,'limit'=>16]);
    $out=[];$busEgressCache=[];$egressCalls=0;
    foreach($result['routes']??[] as $r){
        $times=or_mm_rail_times($r);
        if(!$times||!isset($startDetails[$times['from']],$targetDetails[$times['to']]))continue;
        $endInfo=$targetDetails[$times['to']];
        $stationPos=['lat'=>(float)$stations[$times['to']][1],
                     'lon'=>(float)$stations[$times['to']][2]];
        if(!$endInfo['needsBus']){
            $walk=(int)$endInfo['walk'];
            $end=['source'=>'foot','station'=>$times['to'],
                 'departure'=>$times['arrival'],'arrival'=>$times['arrival']+$walk,
                 'legs'=>[],'geometry'=>[]];
            or_mm_insert_walk($end['legs'],$end['geometry'],$stationPos,$to,
                $stations[$times['to']][0],'Destination',$times['arrival'],$walk);
        }else{
            $key=$times['to'].'|'.intdiv($times['arrival'],900);
            if(!array_key_exists($key,$busEgressCache)){
                $busEgressCache[$key]=null;
                if(++$egressCalls<=3)$busEgressCache[$key]=$lookup(
                    $db,$stationPos,$to,$times['arrival']+180,7200,$walkSpeed);
            }
            $end=$busEgressCache[$key];
            if($end===null)continue;
            $end['station']=$times['to'];
        }
        $composed=or_mm_compose($r,$from,$to,$startDetails[$times['from']],$end,$now,$buffer);
        if($composed!==null)$out[$composed['clearRouteId']]=$composed;
    }
    $out=array_values($out);
    usort($out,static fn($a,$b)=>($a['summary']['travelTimeInSeconds']??PHP_INT_MAX)
                                <=>($b['summary']['travelTimeInSeconds']??PHP_INT_MAX));
    return ['routes'=>array_slice($out,0,3),'clearRoutePlanner'=>'OpenRoad-multimodal',
            'clearRouteDataStatus'=>'scheduled','clearRouteCoverage'=>'bus-rail-bus',
            'clearRouteResultLimit'=>3,'clearRouteRefining'=>false,
            'railCalendarThrough'=>$meta['through']];
}
