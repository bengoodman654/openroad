<?php
/** Read-only probe of v0.2.9 staged router on live timetable. */
declare(strict_types=1);
if (PHP_SAPI!=='cli'||count($argv)!==3)exit(2);
require_once $argv[1];
$db=openroad_db();
try{$db->exec("SET SESSION max_statement_time=0.75");}catch(Throwable $ignored){}
$ds=openroad_region_dataset($db,"south_west");
$now=or_current_seconds();
$start=microtime(true);
or_route_deadline($start+4.0);
$a=or_stop_map(or_nearby_stops($db,$ds,51.438,-2.607,1100,24));
$b=or_stop_map(or_nearby_stops($db,$ds,51.459,-2.627,1100,24));
try{
  $direct=or_direct_candidates($db,$ds,$a,$b,$now,7200);
  $seed=or_first_leg_seeds($db,$ds,$a,$now,1.35,3600,3500);
  $legs=or_second_leg_candidates($db,$ds,$seed,$b,$now,180,2000);
  $matches=0;
  foreach($legs as $leg){
    foreach($seed[$leg["transfer_stop"]]??[] as $first){
      if($first["trip_id"]===$leg["trip_id"])continue;
      $access=(int)ceil(($a[$first["board_stop"]]["distance"]??999999)/1.35);
      $egress=(int)ceil(($b[$leg["alight_stop"]]["distance"]??999999)/1.35);
      if($first["depart_sec"]>=$now+$access &&
         $leg["depart_sec"]>=$first["transfer_arrive"]+180 &&
         $leg["depart_sec"]<=$first["transfer_arrive"]+4500 &&
         $access+$egress<=600)$matches++;
    }
  }
  echo "STAGED_LIVE ".$argv[2]." direct=".count($direct).
       " valid_transfers=".$matches." transfer_stops=".count($seed).
       " seconds=".count($legs).
       " ms=".(int)round((microtime(true)-$start)*1000)."\n";
}catch(Throwable $e){
  echo "STAGED_LIVE ".$argv[2]." outcome=ERROR class=".get_class($e).
       " code=".preg_replace("/[^a-zA-Z0-9_]/","",(string)$e->getCode())."\n";
  exit(3);
}
