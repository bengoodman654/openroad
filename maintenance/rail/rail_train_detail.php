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
        $q=$db->prepare('SELECT points FROM rail_shapes WHERE shape_id=? LIMIT 1');
        $q->execute([$info['shape_id']]);
        $blob=$q->fetchColumn();
        if(is_string($blob)){
            $points=json_decode((string)@gzuncompress($blob),true,24);
            if(is_array($points)&&count($points)>=2&&count($points)<=2400){
                $fromStation=$stations[$from];$toStation=$stations[$to];
                $snap=static function(array $target,array $poly,int $offset):array{
                    $best=-1;$distance=1e9;
                    for($i=$offset;$i<count($poly);$i++){
                        $p=$poly[$i];
                        if(!is_array($p)||count($p)<2)continue;
                        $d=or_rail_km((float)$target[1],(float)$target[2],(float)$p[0],(float)$p[1]);
                        if($d<$distance){$distance=$d;$best=$i;}
                    }
                    return [$best,$distance];
                };
                [$i,$distA]=$snap($fromStation,$points,0);
                [$j,$distB]=$i>=0?$snap($toStation,$points,$i+1):[-1,INF];
                if($j>$i && $distA<2 && $distB<2){
                    $slice=array_slice($points,$i,$j-$i+1);
                    foreach($slice as $p)$routePoints[]=['latitude'=>(float)$p[0],'longitude'=>(float)$p[1]];
                    if(count($routePoints)<2)$routePoints=[];
                }
            }
        }
    }
    return ['ok'=>true,'tripId'=>$tripId,'fromCrs'=>$from,'toCrs'=>$to,
        'departureEpoch'=>$departureEpoch,'headsign'=>(string)$info['headsign'],
        'calls'=>$stops,'routePoints'=>$routePoints,
        'geometryStatus'=>$routePoints?'schematic':'stations_only',
        'geometryMessage'=>$routePoints?'Published railway timetable shape through passing stations; not exact track geometry':'Passing-point shape unavailable; only station positions are shown',
        'source'=>'GB Transit / RDG scheduled railway timetable',
        'calendarThrough'=>$meta['through']];
}
