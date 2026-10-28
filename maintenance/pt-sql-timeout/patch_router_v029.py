#!/usr/bin/env python3
"""Repair non-monotone timetable candidate coverage caused by global LIMIT.
Apply strictly AFTER v0.2.8 on a staged copy; never touches original ZIP.
"""
from pathlib import Path
import sys

router=Path(sys.argv[1])
src=router.read_text(encoding='utf-8')
def replace_function(src,name,next_name,body):
    first='function '+name+'('
    assert src.count(first)==1, 'Unsupported baseline: '+name
    a=src.index(first);b=src.index('function '+next_name+'(',a)
    return src[:a]+body.strip()+'\n\n'+src[b:]

BOARDINGS=r'''
function or_active_boardings(PDO $db,int $ds,array $stopIds,int $now,int $window,int $max=800): array {
    if(!$stopIds)return [];
    or_route_check_budget();
    // IMPORTANT: one global LIMIT across additional stops can erase
    // otherwise available journeys. Budget per stop, not per entire area.
    // The active-service join happens BEFORE LIMIT so inactive trips cannot
    // crowd out today's departures. All lookups use the stop/departure index.
    $perStop=$max<=800?24:($max<=1200?36:48);
    $perStop=max(8,min(48,$perStop));
    $sql='SELECT b.trip_id,b.stop_id board_stop,b.stop_sequence board_seq,
                 b.departure_sec depart_sec,
                 t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
          FROM or_stop_times b FORCE INDEX(idx_stop_depart_cover)
          JOIN or_trips t ON t.dataset_id=b.dataset_id AND t.trip_id=b.trip_id
          JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND
               sd.service_id=t.service_id AND sd.service_date=?
          JOIN or_routes r ON r.dataset_id=t.dataset_id AND
               r.route_id=t.route_id
          WHERE b.dataset_id=? AND b.stop_id=?
            AND b.departure_sec BETWEEN ? AND ?
          ORDER BY b.departure_sec LIMIT '.$perStop;
    $q=$db->prepare($sql);
    $out=[];$date=or_active_date();
    foreach(array_slice(array_values(array_unique($stopIds)),0,40) as $stop){
        or_route_check_budget();
        $q->execute([$date,$ds,$stop,$now,$now+$window]);
        foreach($q as $row)$out[]=$row;
    }
    // Deterministic across array order / different inclusion sets.
    usort($out,static fn($a,$b)=>
        ((int)$a['depart_sec']<=>(int)$b['depart_sec'])
        ?:strcmp((string)$a['board_stop'],(string)$b['board_stop'])
        ?:strcmp((string)$a['trip_id'],(string)$b['trip_id']));
    or_route_check_budget();
    return $out;
}
'''
ARRIVALS=r'''
function or_active_arrivals(PDO $db,int $ds,array $stopIds,int $now,int $window,int $max): array {
    if(!$stopIds)return [];
    or_route_check_budget();
    $perStop=$max<=420?24:48;
    $sql='SELECT a.trip_id,a.stop_id alight_stop,a.stop_sequence alight_seq,
                 a.arrival_sec arrive_sec,
                 t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
          FROM or_stop_times a FORCE INDEX(idx_stop_arrive)
          JOIN or_trips t ON t.dataset_id=a.dataset_id AND t.trip_id=a.trip_id
          JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND
               sd.service_id=t.service_id AND sd.service_date=?
          JOIN or_routes r ON r.dataset_id=t.dataset_id AND
               r.route_id=t.route_id
          WHERE a.dataset_id=? AND a.stop_id=?
            AND a.arrival_sec BETWEEN ? AND ?
          ORDER BY a.arrival_sec LIMIT '.$perStop;
    $q=$db->prepare($sql);
    $out=[];$date=or_active_date();
    foreach(array_slice(array_values(array_unique($stopIds)),0,40) as $stop){
        or_route_check_budget();
        $q->execute([$date,$ds,$stop,$now,$now+$window]);
        foreach($q as $row)$out[]=$row;
    }
    usort($out,static fn($a,$b)=>
        ((int)$a['arrive_sec']<=>(int)$b['arrive_sec'])
        ?:strcmp((string)$a['alight_stop'],(string)$b['alight_stop'])
        ?:strcmp((string)$a['trip_id'],(string)$b['trip_id']));
    or_route_check_budget();
    return $out;
}
'''
src=replace_function(src,'or_active_boardings','or_trip_stop_matches',BOARDINGS)
src=replace_function(src,'or_active_arrivals','or_direct_candidates',ARRIVALS)

# Round-robin among boarding stops before a bounded amount of per-trip
# expansion. This avoids 24-stop searches excluding every useful trip from
# the original 10 stops simply because extra stops have earlier departures.
sig="$seeds=[];$rowCount=0;\n    foreach($boards as $board){"
replacement='''$byStop=[];
    foreach($boards as $board)$byStop[$board['board_stop']][]=$board;
    $ordered=[];
    for($round=0;$round<48;$round++){
        foreach($byStop as $group){
            if(isset($group[$round]))$ordered[]=$group[$round];
        }
    }
    $seeds=[];$rowCount=0;
    foreach($ordered as $board){'''
assert src.count(sig)==1, 'Unexpected seed ordering'
src=src.replace(sig,replacement)
needle="if(++$rowCount>min(24000,max(2500,$rowLimit*2)))break 2;"
assert src.count(needle)==1, 'Unexpected seed expansion cap'
src=src.replace(needle,"if(++$rowCount>min(48000,max(14000,$rowLimit*4)))break 2;")
if src.count('function or_active_boardings(')!=1 or src.count('function or_active_arrivals(')!=1:
    raise SystemExit('Malformed result')
router.write_text(src,encoding='utf-8')
print("Per-stop active boarding and arrival budgets applied safely.")
