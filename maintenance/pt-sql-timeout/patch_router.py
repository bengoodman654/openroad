#!/usr/bin/env python3
"""Bounded GTFS SQL search for OpenRoad v0.2.5; exact source anchors only.

No data imports, no schema changes, no API changes. This patch changes only
three expensive candidate functions and skips redundant full transfer queries
when a direct journey exists. A read-only baseline and deployment rollback
must be established separately.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROUTER=Path(sys.argv[1])
original=ROUTER.read_text(encoding="utf-8")

def replace_function(code: str, name: str, next_name: str, body: str) -> str:
    start=code.find("function "+name+"(")
    end=code.find("function "+next_name+"(", start)
    if start<0 or end<0 or code.count("function "+name+"(")!=1:
        raise SystemExit("Unrecognised original router function: "+name)
    return code[:start]+body.strip()+"\n\n"+code[end:]

HELPER=r"""
/** A bounded, index-driven list of active boardings (no stop-times self-join).
 * Using a limited derived table prevents SELECT LIMIT from being applied only
 * after a very large intermediate Cartesian expansion of trip stops.
 */
function or_active_boardings(PDO $db,int $ds,array $stopIds,int $now,int $window,int $max=800): array {
    if(!$stopIds)return [];
    or_route_check_budget();
    $max=max(40,min(2500,$max));
    $sql='SELECT b.trip_id,b.stop_id board_stop,b.stop_sequence board_seq,b.departure_sec depart_sec,
          t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
          FROM (
            SELECT s.dataset_id,s.trip_id,s.stop_id,s.stop_sequence,s.departure_sec
            FROM or_stop_times s FORCE INDEX(idx_stop_depart_cover)
            WHERE s.dataset_id=? AND s.stop_id IN ('.or_in($stopIds).')
              AND s.departure_sec BETWEEN ? AND ?
            ORDER BY s.departure_sec LIMIT '.$max.'
          ) b
          JOIN or_trips t ON t.dataset_id=b.dataset_id AND t.trip_id=b.trip_id
          JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=?
          JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id
          ORDER BY b.departure_sec';
    $q=$db->prepare($sql);
    $q->execute([$ds,...$stopIds,$now,$now+$window,or_active_date()]);
    or_route_check_budget();
    return $q->fetchAll();
}
/** Scan only stop-times for already bounded trip IDs via their PK index. */
function or_trip_stop_matches(PDO $db,int $ds,array $tripIds,?array $stopIds=null): array {
    if(!$tripIds || $stopIds===[])return [];
    $out=[];
    foreach(array_chunk(array_values(array_unique($tripIds)),80) as $group){
        or_route_check_budget();
        $sql='SELECT st.trip_id,st.stop_id,st.stop_sequence,st.arrival_sec,st.departure_sec
              FROM or_stop_times st FORCE INDEX(PRIMARY)
              WHERE st.dataset_id=? AND st.trip_id IN ('.or_in($group).')';
        $args=[$ds,...$group];
        if($stopIds!==null){
            $sql.=' AND st.stop_id IN ('.or_in($stopIds).')';
            $args=[...$args,...$stopIds];
        }
        $q=$db->prepare($sql);$q->execute($args);
        foreach($q as $r)$out[$r['trip_id']][]=$r;
        or_route_check_budget();
    }
    return $out;
}
/** Destination-driven arrivals avoid joining all transfer stops to all trips. */
function or_active_arrivals(PDO $db,int $ds,array $stopIds,int $now,int $window,int $max): array {
    if(!$stopIds)return [];
    or_route_check_budget();
    $max=max(40,min(1500,$max));
    $sql='SELECT a.trip_id,a.stop_id alight_stop,a.stop_sequence alight_seq,a.arrival_sec arrive_sec,
          t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
          FROM (
            SELECT s.dataset_id,s.trip_id,s.stop_id,s.stop_sequence,s.arrival_sec
            FROM or_stop_times s FORCE INDEX(idx_stop_arrive)
            WHERE s.dataset_id=? AND s.stop_id IN ('.or_in($stopIds).')
              AND s.arrival_sec BETWEEN ? AND ?
            ORDER BY s.arrival_sec LIMIT '.$max.'
          ) a
          JOIN or_trips t ON t.dataset_id=a.dataset_id AND t.trip_id=a.trip_id
          JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=?
          JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id
          ORDER BY a.arrival_sec';
    $q=$db->prepare($sql);
    $q->execute([$ds,...$stopIds,$now,$now+$window,or_active_date()]);
    or_route_check_budget();
    return $q->fetchAll();
}
"""

DIRECT=r"""
function or_direct_candidates(PDO $db,int $ds,array $orig,array $dest,int $now,int $window=10800): array {
    $origIds=array_keys($orig);$destIds=array_keys($dest);
    if(!$origIds||!$destIds)return [];
    // A few hundred bounded scheduled boardings suffice for the fast phase.
    // The full phase admits a larger pool, without unbounded trip self-joins.
    $boards=or_active_boardings($db,$ds,$origIds,$now,$window,$window<=7200?1200:2400);
    if(!$boards)return [];
    $tripStops=or_trip_stop_matches($db,$ds,array_column($boards,'trip_id'),$destIds);
    $out=[];
    foreach($boards as $board){
        or_route_check_budget();
        foreach($tripStops[$board['trip_id']]??[] as $alight){
            if((int)$alight['stop_sequence']<=(int)$board['board_seq'])continue;
            $row=$board;
            $row['alight_stop']=$alight['stop_id'];
            $row['alight_seq']=$alight['stop_sequence'];
            $row['arrive_sec']=$alight['arrival_sec'];
            $out[]=$row;
            if(count($out)>=2600)return $out;
        }
    }
    return $out;
}
"""

FIRST=r"""
function or_first_leg_seeds(PDO $db,int $ds,array $orig,int $now,float $walkSpeed,int $window=7200,int $rowLimit=12000): array {
    if(!$orig)return [];
    $boardLimit=$rowLimit<=3500?260:650;
    $boards=or_active_boardings($db,$ds,array_keys($orig),$now,$window,$boardLimit);
    if(!$boards)return [];
    $tripStops=or_trip_stop_matches($db,$ds,array_column($boards,'trip_id'));
    $seeds=[];$rowCount=0;
    foreach($boards as $board){
        or_route_check_budget();
        $access=(int)ceil($orig[$board['board_stop']]['distance']/$walkSpeed);
        if((int)$board['depart_sec']<$now+$access)continue;
        foreach($tripStops[$board['trip_id']]??[] as $x){
            if((int)$x['stop_sequence']<=(int)$board['board_seq'])continue;
            $r=$board;
            $r['transfer_stop']=$x['stop_id'];
            $r['transfer_seq']=$x['stop_sequence'];
            $r['transfer_arrive']=$x['arrival_sec'];
            $r['access_sec']=$access;
            $sid=$r['transfer_stop'];
            $seeds[$sid]??=[];$seeds[$sid][]=$r;
            if(count($seeds[$sid])>5){
                usort($seeds[$sid],fn($a,$b)=>(int)$a['transfer_arrive']<=>(int)$b['transfer_arrive']);
                $seeds[$sid]=array_slice($seeds[$sid],0,5);
            }
            if(++$rowCount>min(24000,max(2500,$rowLimit*2)))break 2;
        }
    }
    return $seeds;
}
"""

SECOND=r"""
function or_second_leg_candidates(PDO $db,int $ds,array $seeds,array $dest,int $now,int $transferBuffer,int $rowLimit=6000): array {
    $trans=array_keys($seeds);$dids=array_keys($dest);
    if(!$trans||!$dids)return [];
    // Searching from a limited set of destination arrivals is much cheaper
    // than executing one expensive self-join per 100 transfer stops.
    $arrivals=or_active_arrivals($db,$ds,$dids,$now+$transferBuffer,
        5*3600-$transferBuffer,$rowLimit<=2000?420:1000);
    if(!$arrivals)return [];
    $tripStops=or_trip_stop_matches($db,$ds,array_column($arrivals,'trip_id'),$trans);
    $out=[];
    foreach($arrivals as $a){
        or_route_check_budget();
        foreach($tripStops[$a['trip_id']]??[] as $b){
            if((int)$b['stop_sequence']>=(int)$a['alight_seq'] ||
               (int)$b['departure_sec']<$now+$transferBuffer)continue;
            $row=$a;
            $row['transfer_stop']=$b['stop_id'];
            $row['board_seq']=$b['stop_sequence'];
            $row['depart_sec']=$b['departure_sec'];
            $out[]=$row;
            if(count($out)>=$rowLimit)return $out;
        }
    }
    return $out;
}
"""

new=original
if "function or_active_boardings(" in new:
    raise SystemExit("Already patched")
if new.count("function or_direct_candidates(")!=1:
    raise SystemExit("Unexpected router layout")
new=new.replace("function or_direct_candidates(",HELPER.strip()+"\n\nfunction or_direct_candidates(",1)
new=replace_function(new,"or_direct_candidates","or_first_leg_seeds",DIRECT)
new=replace_function(new,"or_first_leg_seeds","or_second_leg_candidates",FIRST)
new=replace_function(new,"or_second_leg_candidates","or_trip_stop_points",SECOND)
before="if($phase!=='fast'||count($candidates)<1){"
after="if(count($candidates)<1){"
if new.count(before)!=1:
    raise SystemExit("Unexpected transfer-search condition")
new=new.replace(before,after,1)
# We always retain the existing server deadline, database limit and public API.
if "or_route_deadline($started+(" not in new:
    raise SystemExit("Route deadline missing")
if new.count("function openroad_plan_bus(")!=1 or len(new)<len(original):
    raise SystemExit("Missing original router functions")
ROUTER.write_text(new,encoding="utf-8")
print("Bounded direct/transfer SQL patch complete; no schema/API changes.")
