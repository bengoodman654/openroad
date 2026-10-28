<?php
/**
 * Read-only, bounded timetable-coverage diagnosis.
 * Representative point pair only; not a public API or source of directions.
 */
declare(strict_types=1);
if (PHP_SAPI!=='cli' || count($argv)!==2) exit(2);
require_once $argv[1];
$db=openroad_db();
try {$db->exec('SET SESSION max_statement_time=0.7');}
catch (Throwable $e) {
    // Some cPanel CLI PDO sessions reject SET SESSION even though the
    // web endpoint has its own statement guard. Bounded read-only probe.
    echo "SQL_OVERRIDE_UNAVAILABLE code=".
         preg_replace('/[^a-zA-Z0-9_]/','',(string)$e->getCode())."\n";
}
$ds=openroad_region_dataset($db,'south_west');
if($ds<=0)exit(4);
$day=or_active_date();
$now=or_current_seconds();
$latA=51.438; $lonA=-2.607; $latB=51.459; $lonB=-2.627;
foreach([10,24] as $max){
    $started=microtime(true);
    or_route_deadline($started+4.0);
    $a=or_stop_map(or_nearby_stops($db,$ds,$latA,$lonA,1100,$max));
    $b=or_stop_map(or_nearby_stops($db,$ds,$latB,$lonB,1100,$max));
    try {
        $boards=or_active_boardings($db,$ds,array_keys($a),$now,7200,800);
        $arrivals=or_active_arrivals($db,$ds,array_keys($b),$now+180,5*3600-180,420);
        $direct=or_direct_candidates($db,$ds,$a,$b,$now,7200);
        $seeds=or_first_leg_seeds($db,$ds,$a,$now,1.35,3600,3500);
        $seconds=or_second_leg_candidates($db,$ds,$seeds,$b,$now,180,2000);
        $physical=0;$timeFeasible=0;$withWalking=0;
        foreach($seconds as $leg){
           foreach($seeds[$leg['transfer_stop']]??[] as $f){
             if($f['trip_id']===$leg['trip_id']) continue;
             $physical++;
             if((int)$leg['depart_sec']>=(int)$f['transfer_arrive']+180 &&
                (int)$leg['depart_sec']<=(int)$f['transfer_arrive']+4500)
                 $timeFeasible++;
             $access=(int)ceil(($a[$f['board_stop']]['distance']??100000)/1.35);
             $egress=(int)ceil(($b[$leg['alight_stop']]['distance']??100000)/1.35);
             if((int)$leg['depart_sec']>=(int)$f['transfer_arrive']+180 &&
                (int)$leg['depart_sec']<=(int)$f['transfer_arrive']+4500 &&
                (int)$f['depart_sec'] >= $now+$access &&
                $access+$egress <=600)$withWalking++;
           }
        }
        echo "COVERAGE radius_m=1100 max_stops=$max origin_stops=".count($a).
             " dest_stops=".count($b)." origin_boardings=".count($boards).
             " destination_arrivals=".count($arrivals)." direct_pairs=".count($direct).
             " transfer_stops=".count($seeds)." second_legs=".count($seconds).
             " same_stop_pairs=".$physical." valid_pairs=".$timeFeasible.
             " within_10min_walk=".$withWalking.
             " elapsed_ms=".(int)round((microtime(true)-$started)*1000)."\n";
    }catch(Throwable $e){
        echo "COVERAGE max_stops=$max outcome=ERROR class=".get_class($e).
             " code=".preg_replace('/[^a-zA-Z0-9_]/','',(string)$e->getCode())."\n";
    }
}
