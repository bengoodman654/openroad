<?php
declare(strict_types=1);
/**
 * Read-only, on-demand timetable and published rail shape for one selected
 * train. No timetable work in the initial journey-planning request.
 */
require_once __DIR__.'/rail_planner.php';

function or_train_detail(string $root,int $tripId,string $from,string $to,int $departureEpoch):array {
    if($tripId<1 || $tripId>10000000 || !preg_match('/^[A-Z]{3}$/D',$from) ||
       !preg_match('/^[A-Z]{3}$/D',$to) || $departureEpoch<1600000000 ||
       abs($departureEpoch-time())>5*86400)throw new InvalidArgumentException('Invalid train selection');
    [$meta,$stations]=or_rail_index($root);
    $path=$root.'/events.sqlite';
    $db=new PDO('sqlite:file:'.$path.'?mode=ro');
    $db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
    $db->exec('PRAGMA query_only=ON');
    $db->exec('PRAGMA busy_timeout=100');
    $q=$db->prepare('SELECT dep FROM events WHERE o=? AND dep=? AND trip=? LIMIT 1');
    $q->execute([$from,$departureEpoch,$tripId]);
    if($q->fetchColumn()===false)throw new RuntimeException('Selected train is no longer in the current timetable');
    $q=$db->prepare('SELECT gtfs_id,headsign,shape_id,calls FROM train_info WHERE trip=? LIMIT 1');
    $q->execute([$tripId]);
    $info=$q->fetch(PDO::FETCH_ASSOC);
    if(!$info)throw new RuntimeException('Train timetable not found');
    $calls=json_decode((string)gzuncompress((string)$info['calls']),true,24);
    if(!is_array($calls)||count($calls)<2||count($calls)>180)
        throw new RuntimeException('Invalid train calling points');
    $startIndex=null;$endIndex=null;
    foreach($calls as $i=>$call){
        if(!is_array($call)||count($call)<3)continue;
        if($startIndex===null && $call[0]===$from)$startIndex=$i;
        if($startIndex!==null && $i>$startIndex && $call[0]===$to){$endIndex=$i;break;}
    }
    if($startIndex===null||$endIndex===null)throw new RuntimeException('Selected calling points do not match this train');
    $base=$departureEpoch-(int)$calls[$startIndex][2];
    $stops=[];
    foreach($calls as $i=>$call){
        $code=(string)$call[0];$station=$stations[$code]??[$code,0,0];
        $arr=$base+(int)$call[1];$dep=$base+(int)$call[2];
        $stops[]=['crs'=>$code,'name'=>(string)$station[0],
            'scheduledArrival'=>date('H:i',$arr),'scheduledDeparture'=>date('H:i',$dep),
            'arrivalEpoch'=>$arr,'departureEpoch'=>$dep,
            'boarding'=>$i===$startIndex,'alighting'=>$i===$endIndex,
            'withinJourney'=>$i>=$startIndex&&$i<=$endIndex];
    }
    $routePoints=[];$quality='schematic';
    // This feed's shapes trace passing stations, not exact track centrelines.
    // Display as such. Never claim this geometry is surveyed railway track.
    if(!empty($info['shape_id'])){
        $q=$db->prepare('SELECT * FROM rail_shapes WHERE shape_id=? LIMIT 1');
        $q->execute([$info['shape_id']]);
        $shapeRow=$q->fetch(PDO::FETCH_ASSOC);
        $blob=$shapeRow['points']??null;
        $quality=(string)($shapeRow['quality']??'schematic');
        if(is_string($blob)){
            $points=json_decode((string)@gzuncompress($blob),true,24);
            if(is_array($points)&&count($points)>=2&&count($points)<=2400){
                $fromStation=$stations[$from];$toStation=$stations[$to];
                // Find the best ordered boarding/alighting pair in one scan.
                // Selecting the globally nearest boarding vertex first can
                // pick the wrong visit on circular or duplicated railway lines.
                $bestBoard=-1;$minFrom=INF;$bestPair=null;$bestCost=INF;
                foreach($points as $pos=>$p){
                    if(!is_array($p)||count($p)<2)continue;
                    $distFrom=or_rail_km((float)$fromStation[1],(float)$fromStation[2],(float)$p[0],(float)$p[1]);
                    if($pos>0 && $bestBoard>=0){
                        $distTo=or_rail_km((float)$toStation[1],(float)$toStation[2],(float)$p[0],(float)$p[1]);
                        $cost=$minFrom+$distTo;
                        if($minFrom<2.0 && $distTo<2.0 && $cost<$bestCost){
                            $bestCost=$cost;$bestPair=[$bestBoard,$pos];
                        }
                    }
                    if($distFrom<$minFrom){$minFrom=$distFrom;$bestBoard=$pos;}
                }
                if($bestPair!==null){
                    [$i,$j]=$bestPair;
                    $slice=array_slice($points,$i,$j-$i+1);
                    foreach($slice as $p)$routePoints[]=['latitude'=>(float)$p[0],'longitude'=>(float)$p[1]];
                    if(count($routePoints)<2)$routePoints=[];
                }
            }
        }
    }
    $track=$routePoints && $quality==='track-aligned';
    $partial=$routePoints && $quality==='partly-track-aligned';
    $status=$track?'track_aligned':($partial?'partly_track_aligned':($routePoints?'schematic':'stations_only'));
    return ['ok'=>true,'tripId'=>$tripId,'fromCrs'=>$from,'toCrs'=>$to,
        'departureEpoch'=>$departureEpoch,'headsign'=>(string)$info['headsign'],
        'calls'=>$stops,'routePoints'=>$routePoints,
        'geometryStatus'=>$status,
        'geometryMessage'=>$track?'Track-aligned railway route from Network Rail GIS (2022 reference). The train’s actual platform track may differ.':
          ($partial?'Partly aligned with surveyed railway track; remaining sections use timetable passing points.':
          ($routePoints?'Published railway timetable shape through passing stations; not exact track geometry':
           'Passing-point shape unavailable; only station positions are shown')),
        'geometrySource'=>$track||$partial?'Network Rail Open Government Licence track centrelines (historic baseline)':'GB Transit scheduled railway schematic',
        'source'=>'GB Transit / RDG scheduled railway timetable',
        'calendarThrough'=>$meta['through']];
}
