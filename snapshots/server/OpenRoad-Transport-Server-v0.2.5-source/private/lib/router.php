<?php
require_once __DIR__ . '/bootstrap.php';

/** A per-request CPU/SQL budget. PHP cannot interrupt an already running remote SQL statement,
 * so journeys.php also sets the database statement limit on a best-effort basis. */
function or_route_deadline(?float $set=null): ?float {
    static $deadline=null;
    if ($set!==null) $deadline=$set;
    return $deadline;
}
function or_route_check_budget(): void {
    $deadline=or_route_deadline();
    if ($deadline!==null && microtime(true)>$deadline)
        throw new RuntimeException('The timetable search exceeded its time budget. Please retry.');
}
function or_route_elapsed_ms(float $start): int { return (int)round((microtime(true)-$start)*1000); }

function or_haversine(float $lat1,float $lon1,float $lat2,float $lon2): float {
    $r=6371000.0;$p1=deg2rad($lat1);$p2=deg2rad($lat2);$dp=deg2rad($lat2-$lat1);$dl=deg2rad($lon2-$lon1);
    $a=sin($dp/2)**2+cos($p1)*cos($p2)*sin($dl/2)**2; return 2*$r*asin(min(1,sqrt($a)));
}
function or_clock(int $sec): string { $sec%=86400; if($sec<0)$sec+=86400; return sprintf('%02d:%02d',intdiv($sec,3600),intdiv($sec%3600,60)); }
function or_walk_speed(string $setting): float { return $setting==='slow'?1.05:($setting==='fast'?1.65:1.35); }
function or_active_date(): string { return date('Y-m-d'); }
function or_current_seconds(): int { return ((int)date('H'))*3600+((int)date('i'))*60+(int)date('s'); }
function or_in(array $items): string { return implode(',',array_fill(0,count($items),'?')); }
function or_stop_map(array $stops): array {$o=[];foreach($stops as $s)$o[$s['stop_id']]=$s;return $o;}
function or_dataset_for_points(PDO $db,float $olat,float $olon,float $dlat,float $dlon): array {
    $a=openroad_region_for_point($olat,$olon);$b=openroad_region_for_point($dlat,$dlon);
    if($a==='london'||$b==='london')throw new RuntimeException('This journey needs national rail and London connections, which are not yet supported by the regional bus server.');
    if($a===null || $b===null)throw new RuntimeException('This journey falls outside the prepared regional bus network.');
    if($a!==$b)throw new RuntimeException('The regional bus server cannot yet route between different regions. National rail connections are planned for the next phase.');
    $region=$a;
    $ds=openroad_region_dataset($db,$region);
    if(!$ds){openroad_enqueue_region($db,$region,'route');throw new RuntimeException('Transport data for this area is being prepared. Try again shortly.');}
    openroad_region_touch($db,$region);return [$ds,$region];
}
function or_cache_key(int $ds,string $region,float $olat,float $olon,float $dlat,float $dlon,array $settings): string {
    $bucket=(int)floor(time()/120);$safe=['maxWalk'=>(int)($settings['maxWalk']??10),'walkSpeed'=>(string)($settings['walkSpeed']??'normal'),'transferBuffer'=>(string)($settings['transferBuffer']??'normal'),'ranking'=>(string)($settings['ranking']??'balanced'),'resultLimit'=>(int)($settings['resultLimit']??3),'phase'=>(string)($settings['phase']??'full')];
    return hash('sha256',implode('|',[$ds,$region,round($olat,4),round($olon,4),round($dlat,4),round($dlon,4),$bucket,json_encode($safe)]));
}
function or_cache_get(PDO $db,string $key): ?array {$q=$db->prepare('SELECT response_json FROM or_journey_cache WHERE cache_key=? AND expires_at>NOW() LIMIT 1');$q->execute([$key]);$v=$q->fetchColumn();if($v===false)return null;$j=json_decode((string)$v,true);return is_array($j)?$j:null;}
function or_cache_put(PDO $db,string $key,string $region,int $ds,array $payload,int $ttl=180): void {$q=$db->prepare('INSERT INTO or_journey_cache(cache_key,region_key,dataset_id,response_json,created_at,expires_at) VALUES(?,?,?,?,NOW(),DATE_ADD(NOW(),INTERVAL ? SECOND)) ON DUPLICATE KEY UPDATE response_json=VALUES(response_json),created_at=NOW(),expires_at=VALUES(expires_at)');$q->execute([$key,$region,$ds,json_encode($payload,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE),$ttl]);}

/**
 * Exact nearest-stop selection inside a geographic box.
 * v0.2.0 used an unordered SQL LIMIT before distance sorting, which could silently discard the
 * stop immediately beside the user in dense areas. We now fetch every stop in the small box,
 * calculate the real great-circle distance, then keep the actual nearest stops.
 */
function or_nearby_stops(PDO $db,int $ds,float $lat,float $lon,float $radius,int $limit=40): array {
    $latDelta=$radius/111320.0; $cos=max(0.2,cos(deg2rad($lat))); $lonDelta=$radius/(111320.0*$cos);
    $s=$db->prepare('SELECT stop_id,stop_name,stop_lat,stop_lon FROM or_stops WHERE dataset_id=? AND stop_lat BETWEEN ? AND ? AND stop_lon BETWEEN ? AND ?');
    $s->execute([$ds,$lat-$latDelta,$lat+$latDelta,$lon-$lonDelta,$lon+$lonDelta]); $out=[];
    foreach($s as $r){$d=or_haversine($lat,$lon,(float)$r['stop_lat'],(float)$r['stop_lon']);if($d<=$radius){$r['distance']=$d;$out[]=$r;}}
    usort($out,fn($a,$b)=>$a['distance']<=>$b['distance']); return array_slice($out,0,$limit);
}

function or_direct_candidates(PDO $db,int $ds,array $orig,array $dest,int $now,int $window=10800): array {
    $oids=array_keys($orig);$dids=array_keys($dest); if(!$oids||!$dids)return [];
    $sql='SELECT b.trip_id,b.stop_id board_stop,b.stop_sequence board_seq,b.departure_sec depart_sec,a.stop_id alight_stop,a.stop_sequence alight_seq,a.arrival_sec arrive_sec,t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
      FROM or_stop_times b JOIN or_trips t ON t.dataset_id=b.dataset_id AND t.trip_id=b.trip_id
      JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=?
      JOIN or_stop_times a ON a.dataset_id=b.dataset_id AND a.trip_id=b.trip_id AND a.stop_sequence>b.stop_sequence
      JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id
      WHERE b.dataset_id=? AND b.stop_id IN ('.or_in($oids).') AND a.stop_id IN ('.or_in($dids).') AND b.departure_sec BETWEEN ? AND ? ORDER BY b.departure_sec LIMIT 2600';
    $params=[or_active_date(),$ds,...$oids,...$dids,$now,$now+$window];$q=$db->prepare($sql);$q->execute($params);return $q->fetchAll();
}
function or_first_leg_seeds(PDO $db,int $ds,array $orig,int $now,float $walkSpeed,int $window=7200,int $rowLimit=12000): array {
    $oids=array_keys($orig);if(!$oids)return [];
    $sql='SELECT b.trip_id,b.stop_id board_stop,b.stop_sequence board_seq,b.departure_sec depart_sec,x.stop_id transfer_stop,x.stop_sequence transfer_seq,x.arrival_sec transfer_arrive,t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
      FROM or_stop_times b JOIN or_trips t ON t.dataset_id=b.dataset_id AND t.trip_id=b.trip_id
      JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=?
      JOIN or_stop_times x ON x.dataset_id=b.dataset_id AND x.trip_id=b.trip_id AND x.stop_sequence>b.stop_sequence
      JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id
      WHERE b.dataset_id=? AND b.stop_id IN ('.or_in($oids).') AND b.departure_sec BETWEEN ? AND ? ORDER BY b.departure_sec,x.stop_sequence LIMIT '.max(500,min(12000,$rowLimit));
    $q=$db->prepare($sql);$q->execute([or_active_date(),$ds,...$oids,$now,$now+$window]);$seeds=[];
    while($r=$q->fetch()){
        $access=(int)ceil($orig[$r['board_stop']]['distance']/$walkSpeed); if((int)$r['depart_sec']<$now+$access)continue;
        $stop=$r['transfer_stop'];$r['access_sec']=$access;
        $seeds[$stop]??=[];$seeds[$stop][]=$r;
        if(count($seeds[$stop])>5){usort($seeds[$stop],fn($a,$b)=>$a['transfer_arrive']<=>$b['transfer_arrive']);$seeds[$stop]=array_slice($seeds[$stop],0,5);}
    }
    return $seeds;
}
function or_second_leg_candidates(PDO $db,int $ds,array $seeds,array $dest,int $now,int $transferBuffer,int $rowLimit=6000): array {
    $trans=array_keys($seeds);$dids=array_keys($dest);if(!$trans||!$dids)return [];$out=[];
    foreach(array_chunk($trans,100) as $chunk){
      or_route_check_budget();
      $sql='SELECT b.trip_id,b.stop_id transfer_stop,b.stop_sequence board_seq,b.departure_sec depart_sec,a.stop_id alight_stop,a.stop_sequence alight_seq,a.arrival_sec arrive_sec,t.route_id,t.shape_id,t.headsign,r.short_name,r.long_name
        FROM or_stop_times b JOIN or_trips t ON t.dataset_id=b.dataset_id AND t.trip_id=b.trip_id
        JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=?
        JOIN or_stop_times a ON a.dataset_id=b.dataset_id AND a.trip_id=b.trip_id AND a.stop_sequence>b.stop_sequence
        JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id
        WHERE b.dataset_id=? AND b.stop_id IN ('.or_in($chunk).') AND a.stop_id IN ('.or_in($dids).') AND b.departure_sec BETWEEN ? AND ? ORDER BY b.departure_sec LIMIT '.max(500,min(6000,$rowLimit));
      $q=$db->prepare($sql);$q->execute([or_active_date(),$ds,...$chunk,...$dids,$now+$transferBuffer,$now+5*3600]);
      while($r=$q->fetch())$out[]=$r;
      or_route_check_budget();
    }
    return $out;
}

function or_trip_stop_points(PDO $db,int $ds,string $trip,int $fromSeq,int $toSeq): array {
    $q=$db->prepare('SELECT s.stop_lat,s.stop_lon FROM or_stop_times st JOIN or_stops s ON s.dataset_id=st.dataset_id AND s.stop_id=st.stop_id WHERE st.dataset_id=? AND st.trip_id=? AND st.stop_sequence BETWEEN ? AND ? ORDER BY st.stop_sequence');
    $q->execute([$ds,$trip,$fromSeq,$toSeq]);$p=[];while($r=$q->fetch())$p[]=['latitude'=>(float)$r['stop_lat'],'longitude'=>(float)$r['stop_lon']];return $p;
}
function or_trip_stop_details(PDO $db,int $ds,string $trip,int $fromSeq,int $toSeq): array {
    $q=$db->prepare('SELECT st.stop_sequence,st.arrival_sec,st.departure_sec,s.stop_id,s.stop_name,s.stop_lat,s.stop_lon FROM or_stop_times st JOIN or_stops s ON s.dataset_id=st.dataset_id AND s.stop_id=st.stop_id WHERE st.dataset_id=? AND st.trip_id=? AND st.stop_sequence BETWEEN ? AND ? ORDER BY st.stop_sequence');$q->execute([$ds,$trip,$fromSeq,$toSeq]);$out=[];while($r=$q->fetch())$out[]=['id'=>$r['stop_id'],'name'=>$r['stop_name'],'lat'=>(float)$r['stop_lat'],'lon'=>(float)$r['stop_lon'],'arrival'=>or_clock((int)$r['arrival_sec']),'departure'=>or_clock((int)$r['departure_sec'])];return $out;
}
function or_shape_segment(PDO $db,int $ds,string $shapeId,float $fromLat,float $fromLon,float $toLat,float $toLon): array {
    if($shapeId==='')return [];
    $q=$db->prepare('SELECT point_lat,point_lon FROM or_shapes WHERE dataset_id=? AND shape_id=? ORDER BY point_sequence');
    $q->execute([$ds,$shapeId]);$pts=[];while($r=$q->fetch())$pts[]=['latitude'=>(float)$r['point_lat'],'longitude'=>(float)$r['point_lon']];
    $n=count($pts);if($n<2)return [];
    // Find the best ordered from/to pair. This is safer on looping routes than independently
    // choosing two nearest points and assuming the indexes happen to be in travel order.
    $bestFromIdx=0;$bestFromDist=INF;$bestA=-1;$bestB=-1;$best=INF;
    for($j=0;$j<$n;$j++){
        $dFrom=or_haversine($fromLat,$fromLon,$pts[$j]['latitude'],$pts[$j]['longitude']);
        if($dFrom<$bestFromDist){$bestFromDist=$dFrom;$bestFromIdx=$j;}
        if($bestFromIdx<$j){
            $dTo=or_haversine($toLat,$toLon,$pts[$j]['latitude'],$pts[$j]['longitude']);$score=$bestFromDist+$dTo;
            if($score<$best){$best=$score;$bestA=$bestFromIdx;$bestB=$j;}
        }
    }
    if($bestA<0||$bestB<=$bestA)return [];
    return array_slice($pts,$bestA,$bestB-$bestA+1);
}
function or_points_distance(array $points): float {$d=0;for($i=1;$i<count($points);$i++)$d+=or_haversine($points[$i-1]['latitude'],$points[$i-1]['longitude'],$points[$i]['latitude'],$points[$i]['longitude']);return $d;}
function or_walk_leg(string $from,string $to,array $a,array $b,int $sec,float $metres): array {return ['mode'=>'foot','from'=>$from,'to'=>$to,'fromLat'=>(float)$a['lat'],'fromLon'=>(float)$a['lon'],'toLat'=>(float)$b['lat'],'toLon'=>(float)$b['lon'],'durationSeconds'=>max(1,$sec),'distanceMetres'=>(int)round($metres),'timeStatus'=>'scheduled','dataSource'=>'OpenRoad walking estimate','geometryStatus'=>$metres>25?'loading':'exact'];}
function or_bus_leg(array $r,array $board,array $alight,float $metres,bool $exact): array {return ['mode'=>'bus','line'=>$r['short_name']!==''?$r['short_name']:$r['long_name'],'destination'=>$r['headsign']??'','from'=>$board['stop_name'],'to'=>$alight['stop_name'],'fromAtco'=>$r['board_stop'],'toAtco'=>$r['alight_stop'],'fromLat'=>(float)$board['stop_lat'],'fromLon'=>(float)$board['stop_lon'],'toLat'=>(float)$alight['stop_lat'],'toLon'=>(float)$alight['stop_lon'],'departure'=>or_clock((int)$r['depart_sec']),'arrival'=>or_clock((int)$r['arrive_sec']),'durationSeconds'=>max(60,(int)$r['arrive_sec']-(int)$r['depart_sec']),'distanceMetres'=>(int)round($metres),'stopCount'=>max(1,(int)$r['alight_seq']-(int)$r['board_seq']),'shapeId'=>$r['shape_id']??'','tripId'=>$r['trip_id']??'','boardSequence'=>(int)($r['board_seq']??0),'alightSequence'=>(int)($r['alight_seq']??0),'timeStatus'=>'scheduled','dataSource'=>'DfT BODS GTFS via OpenRoad server','geometryStatus'=>$exact?'exact':'fallback'];}

function or_get_stop(PDO $db,int $ds,string $sid): ?array {
    $q=$db->prepare('SELECT stop_id,stop_name,stop_lat,stop_lon FROM or_stops WHERE dataset_id=? AND stop_id=? LIMIT 1');$q->execute([$ds,$sid]);$s=$q->fetch();return $s?:null;
}
function or_make_journey(PDO $db,int $ds,float $olat,float $olon,float $dlat,float $dlon,array $orig,array $dest,array $first,?array $second,float $walkSpeed,int $now): array {
    $b=or_get_stop($db,$ds,$first['board_stop']);$fa=or_get_stop($db,$ds,$first['alight_stop']);$end=or_get_stop($db,$ds,$second?$second['alight_stop']:$first['alight_stop']);
    if(!$b||!$fa||!$end)throw new RuntimeException('A timetable stop could not be resolved.');
    $legs=[];$tlegs=[];$instructions=[];$metres=0;$pointIndex=0;
    $access=$orig[$first['board_stop']]['distance']; if($access>20){$p=[['latitude'=>$olat,'longitude'=>$olon],['latitude'=>(float)$b['stop_lat'],'longitude'=>(float)$b['stop_lon']]];$legs[]=['points'=>$p];$tlegs[]=or_walk_leg('Your location',$b['stop_name'],['lat'=>$olat,'lon'=>$olon],['lat'=>$b['stop_lat'],'lon'=>$b['stop_lon']],(int)ceil($access/$walkSpeed),$access);$instructions[]=['pointIndex'=>$pointIndex,'routeOffsetInMeters'=>(int)$metres,'travelTimeInSeconds'=>0,'message'=>'Walk to '.$b['stop_name'],'maneuver'=>'STRAIGHT','instructionType'=>'TRANSIT'];$metres+=$access;$pointIndex+=count($p);}
    $p1=or_shape_segment($db,$ds,(string)($first['shape_id']??''),(float)$b['stop_lat'],(float)$b['stop_lon'],(float)$fa['stop_lat'],(float)$fa['stop_lon']);$exact1=count($p1)>=2;if(!$exact1)$p1=or_trip_stop_points($db,$ds,$first['trip_id'],(int)$first['board_seq'],(int)$first['alight_seq']);$d1=or_points_distance($p1);$legs[]=['points'=>$p1];$bl1=or_bus_leg($first,$b,$fa,$d1,$exact1);$bl1['stops']=or_trip_stop_details($db,$ds,$first['trip_id'],(int)$first['board_seq'],(int)$first['alight_seq']);$tlegs[]=$bl1;$instructions[]=['pointIndex'=>$pointIndex,'routeOffsetInMeters'=>(int)$metres,'travelTimeInSeconds'=>0,'message'=>'Bus '.($first['short_name']?:$first['long_name']).' to '.$fa['stop_name'],'maneuver'=>'STRAIGHT','instructionType'=>'TRANSIT'];$metres+=$d1;$pointIndex+=count($p1);
    if($second){$sb=$fa;$sa=$end;$second['board_stop']=$first['alight_stop'];$p2=or_shape_segment($db,$ds,(string)($second['shape_id']??''),(float)$sb['stop_lat'],(float)$sb['stop_lon'],(float)$sa['stop_lat'],(float)$sa['stop_lon']);$exact2=count($p2)>=2;if(!$exact2)$p2=or_trip_stop_points($db,$ds,$second['trip_id'],(int)$second['board_seq'],(int)$second['alight_seq']);$d2=or_points_distance($p2);$legs[]=['points'=>$p2];$bl2=or_bus_leg($second,$sb,$sa,$d2,$exact2);$bl2['stops']=or_trip_stop_details($db,$ds,$second['trip_id'],(int)$second['board_seq'],(int)$second['alight_seq']);$tlegs[]=$bl2;$instructions[]=['pointIndex'=>$pointIndex,'routeOffsetInMeters'=>(int)$metres,'travelTimeInSeconds'=>0,'message'=>'Change to bus '.($second['short_name']?:$second['long_name']).' to '.$sa['stop_name'],'maneuver'=>'STRAIGHT','instructionType'=>'TRANSIT'];$metres+=$d2;$pointIndex+=count($p2);}
    $egress=$dest[$end['stop_id']]['distance']??or_haversine((float)$end['stop_lat'],(float)$end['stop_lon'],$dlat,$dlon); if($egress>20){$p=[['latitude'=>(float)$end['stop_lat'],'longitude'=>(float)$end['stop_lon']],['latitude'=>$dlat,'longitude'=>$dlon]];$legs[]=['points'=>$p];$tlegs[]=or_walk_leg($end['stop_name'],'Destination',['lat'=>$end['stop_lat'],'lon'=>$end['stop_lon']],['lat'=>$dlat,'lon'=>$dlon],(int)ceil($egress/$walkSpeed),$egress);$instructions[]=['pointIndex'=>$pointIndex,'routeOffsetInMeters'=>(int)$metres,'travelTimeInSeconds'=>0,'message'=>'Walk to your destination','maneuver'=>'STRAIGHT','instructionType'=>'TRANSIT'];$metres+=$egress;}
    $leave=max($now,(int)$first['depart_sec']-(int)ceil($access/$walkSpeed));$arr=(int)($second?$second['arrive_sec']:$first['arrive_sec'])+(int)ceil($egress/$walkSpeed);$changes=$second?1:0;
    return ['summary'=>['travelTimeInSeconds'=>max(60,$arr-$leave),'lengthInMeters'=>(int)round($metres)],'legs'=>$legs,'transitLegs'=>$tlegs,'guidance'=>['instructions'=>$instructions],'clearRouteTransit'=>true,'clearRouteDeparture'=>or_clock($leave),'clearRouteArrival'=>or_clock($arr),'clearRouteDataStatus'=>'scheduled','clearRouteLiveStatus'=>'loading','clearRouteDataSource'=>'OpenRoad Transport Server · DfT BODS GTFS','clearRouteDataNote'=>'Scheduled journey from the pre-indexed official DfT/BODS timetable; walking geometry and live data are enriched afterwards','_changes'=>$changes,'_leave'=>$leave,'_arr'=>$arr,'_walk_sec'=>(int)ceil(($access+$egress)/$walkSpeed)];
}
function or_candidate_score(array $c,string $rank,int $changePenalty): float {
    $arrival=(int)$c['_arr'];$changes=(int)$c['_changes'];$walk=(int)$c['_walk_sec'];
    if($rank==='changes')return $changes*10000000.0+$arrival+$walk*.35;
    if($rank==='quickest')return $arrival+$walk*.02;
    return $arrival+$changes*$changePenalty+$walk*.80;
}
function or_candidate_signature(array $c): string {
    // Include the concrete trip/departure as well as stops. Two departures of the same route
    // must not share an ID, otherwise a fuller async search can make the selected card point
    // at a different physical journey on the map.
    $a=$c['first'];$s=($a['short_name']?:$a['long_name']).':'.($a['trip_id']??'').':'.($a['depart_sec']??'').':'.$a['board_stop'].'>'.$a['alight_stop'];
    if($c['second']){$b=$c['second'];$s.='|'.($b['short_name']?:$b['long_name']).':'.($b['trip_id']??'').':'.($b['depart_sec']??'').':'.$b['transfer_stop'].'>'.$b['alight_stop'];}
    return $s;
}

function openroad_plan_bus(PDO $db,float $olat,float $olon,float $dlat,float $dlon,array $settings=[]): array {
    $started=microtime(true);$phase=(string)($settings['phase']??'full');
    // The client gives this request a 3s connect + 6s read budget; leave time for JSON and rendering.
    or_route_deadline($started+($phase==='fast'?4.5:6.5));
    [$ds,$region]=or_dataset_for_points($db,$olat,$olon,$dlat,$dlon);
    $stage=[];
    $cacheKey=or_cache_key($ds,$region,$olat,$olon,$dlat,$dlon,$settings);$cached=or_cache_get($db,$cacheKey);
    if($cached!==null){$cached['clearRouteCache']='hit';$cached['clearRouteTimingMs']=or_route_elapsed_ms($started);$cached['clearRouteStagesMs']=['cache'=>or_route_elapsed_ms($started)];return $cached;}
    $stage['cache_and_region']=or_route_elapsed_ms($started);or_route_check_budget();
    $walkSpeed=or_walk_speed((string)($settings['walkSpeed']??'normal'));$maxWalkMin=max(3,min(60,(int)($settings['maxWalk']??10)));$walkBudget=$maxWalkMin*60;$radius=min(4000,$walkBudget*$walkSpeed);$transferBuffer=($settings['transferBuffer']??'normal')==='cautious'?480:180;$now=or_current_seconds();$limit=max(3,min(9,(int)($settings['resultLimit']??3)));
    $stopLimit=$phase==='fast'?10:24;$origList=or_nearby_stops($db,$ds,$olat,$olon,$radius,$stopLimit);$destList=or_nearby_stops($db,$ds,$dlat,$dlon,$radius,$stopLimit);if(!$origList||!$destList)throw new RuntimeException('No suitable bus stops were found within the walking limit.');$orig=or_stop_map($origList);$dest=or_stop_map($destList);
    $stage['nearby_stops']=or_route_elapsed_ms($started);or_route_check_budget();
    $candidates=[];$directRows=or_direct_candidates($db,$ds,$orig,$dest,$now,$phase==='fast'?7200:10800);
    $stage['direct_query']=or_route_elapsed_ms($started);or_route_check_budget();
    foreach($directRows as $r){$access=(int)ceil($orig[$r['board_stop']]['distance']/$walkSpeed);$egress=(int)ceil($dest[$r['alight_stop']]['distance']/$walkSpeed);if($access+$egress>$walkBudget)continue;if((int)$r['depart_sec']<$now+$access)continue;$candidates[]=['first'=>$r,'second'=>null,'_changes'=>0,'_walk_sec'=>$access+$egress,'_arr'=>(int)$r['arrive_sec']+$egress];}
    // Fast phase returns usable direct routes immediately. If there are none, do a small transfer
    // search rather than leaving the user with an empty spinner. The full phase always explores transfers.
    if($phase!=='fast'||count($candidates)<1){$seeds=or_first_leg_seeds($db,$ds,$orig,$now,$walkSpeed,$phase==='fast'?3600:7200,$phase==='fast'?3500:12000);foreach(or_second_leg_candidates($db,$ds,$seeds,$dest,$now,$transferBuffer,$phase==='fast'?2000:6000) as $second){$sid=$second['transfer_stop'];foreach($seeds[$sid]??[] as $first){if($first['trip_id']===$second['trip_id'])continue;if((int)$second['depart_sec']<(int)$first['transfer_arrive']+$transferBuffer||(int)$second['depart_sec']>(int)$first['transfer_arrive']+4500)continue;$egress=(int)ceil($dest[$second['alight_stop']]['distance']/$walkSpeed);$walk=(int)$first['access_sec']+$egress;if($walk>$walkBudget)continue;$first2=$first;$first2['alight_stop']=$first['transfer_stop'];$first2['alight_seq']=$first['transfer_seq'];$first2['arrive_sec']=$first['transfer_arrive'];$second2=$second;$second2['board_stop']=$sid;$candidates[]=['first'=>$first2,'second'=>$second2,'_changes'=>1,'_walk_sec'=>$walk,'_arr'=>(int)$second['arrive_sec']+$egress];}}}
    $stage['transfer_search']=or_route_elapsed_ms($started);or_route_check_budget();
    if(!$candidates)throw new RuntimeException('No bus journey was found for the selected time and walking limit.');$rank=(string)($settings['ranking']??'balanced');$penalty=($settings['transferBuffer']??'normal')==='cautious'?720:480;usort($candidates,fn($a,$b)=>or_candidate_score($a,$rank,$penalty)<=>or_candidate_score($b,$rank,$penalty));
    $seen=[];$chosen=[];foreach($candidates as $c){$sig=or_candidate_signature($c);if(isset($seen[$sig]))continue;$seen[$sig]=true;$c['_signature']=$sig;$chosen[]=$c;if(count($chosen)>=$limit+1)break;}$hasMore=count($chosen)>$limit;if($hasMore)$chosen=array_slice($chosen,0,$limit);
    $routes=[];foreach($chosen as $c){$j=or_make_journey($db,$ds,$olat,$olon,$dlat,$dlon,$orig,$dest,$c['first'],$c['second'],$walkSpeed,$now);unset($j['_changes'],$j['_leave'],$j['_arr'],$j['_walk_sec']);$j['clearRouteId']=substr(hash('sha256',$c['_signature']),0,20);$j['clearRouteLabel']=count($routes)===0?'Recommended':'Public transport alternative';$routes[]=$j;}
    $stage['journey_assembly']=or_route_elapsed_ms($started);or_route_check_budget();
    $result=['routes'=>$routes,'clearRoutePlanner'=>'OpenRoad-server','clearRouteRegion'=>$region,'clearRouteHasMore'=>$hasMore,'clearRouteResultLimit'=>$limit,'clearRouteRefining'=>$phase==='fast','serverDatasetUpdated'=>openroad_meta($db,'updated_at',''),'clearRouteTimingMs'=>or_route_elapsed_ms($started),'clearRouteStagesMs'=>$stage,'clearRouteCache'=>'miss'];
    // Cache failure should never invalidate a journey already calculated.
    try { or_cache_put($db,$cacheKey,$region,$ds,$result,$phase==='fast'?75:240); }
    catch(Throwable $e) { openroad_log_error($e); }
    return $result;
}

function or_normalise_line(string $s): string { return strtoupper(preg_replace('/[^A-Z0-9]/i','',trim($s))); }
function or_service_trip_stops(PDO $db,int $ds,string $trip,string $direction): array {
    $q=$db->prepare('SELECT st.stop_sequence,s.stop_id,s.stop_name,s.stop_lat,s.stop_lon FROM or_stop_times st JOIN or_stops s ON s.dataset_id=st.dataset_id AND s.stop_id=st.stop_id WHERE st.dataset_id=? AND st.trip_id=? ORDER BY st.stop_sequence');$q->execute([$ds,$trip]);$out=[];while($r=$q->fetch())$out[]=['id'=>$r['stop_id'],'name'=>$r['stop_name'],'lat'=>(float)$r['stop_lat'],'lon'=>(float)$r['stop_lon'],'direction'=>$direction];return $out;
}
function or_service_timetable(PDO $db,int $ds,string $routeId,string $nearestStop,int $now): array {
    $sql='SELECT st.departure_sec,t.headsign,t.direction_id FROM or_stop_times st JOIN or_trips t ON t.dataset_id=st.dataset_id AND t.trip_id=st.trip_id JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=? WHERE st.dataset_id=? AND st.stop_id=? AND t.route_id=? AND st.departure_sec BETWEEN ? AND ? ORDER BY st.departure_sec LIMIT 12';
    $q=$db->prepare($sql);$q->execute([or_active_date(),$ds,$nearestStop,$routeId,$now-60,$now+6*3600]);$deps=[];while($r=$q->fetch())$deps[]=['time'=>or_clock((int)$r['departure_sec']),'destination'=>$r['headsign'],'direction'=>(string)$r['direction_id']==='1'?'inbound':'outbound'];return $deps;
}
function openroad_bus_service(PDO $db,string $line,float $lat,float $lon): array {
    $region=openroad_region_for_point($lat,$lon);if($region===null||$region==='london')throw new RuntimeException('No prepared regional bus timetable is available here.');$ds=openroad_region_dataset($db,$region);if(!$ds){openroad_enqueue_region($db,$region,'bus-service');throw new RuntimeException('Transport data for this area is being prepared.');}openroad_region_touch($db,$region);$clean=or_normalise_line($line);if($clean==='')throw new RuntimeException('Enter a bus number or route name.');
    $q=$db->prepare('SELECT route_id,short_name,long_name FROM or_routes WHERE dataset_id=? AND (LOWER(short_name)=LOWER(?) OR LOWER(long_name) LIKE LOWER(?)) LIMIT 100');$q->execute([$ds,trim($line),'%'.trim($line).'%']);$routeRows=[];while($r=$q->fetch()){if(or_normalise_line((string)$r['short_name'])===$clean||or_normalise_line((string)$r['long_name'])===$clean||stripos((string)$r['long_name'],trim($line))!==false)$routeRows[]=$r;}if(!$routeRows)throw new RuntimeException('No scheduled route was found for bus '.trim($line).'.');
    $routeIds=array_column($routeRows,'route_id');$cos=max(.2,cos(deg2rad($lat)));
    $sql='SELECT t.trip_id,t.route_id,t.shape_id,t.headsign,t.direction_id,MIN(POW(s.stop_lat-?,2)+POW((s.stop_lon-?)*?,2)) d2 FROM or_trips t JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=? JOIN or_stop_times st ON st.dataset_id=t.dataset_id AND st.trip_id=t.trip_id JOIN or_stops s ON s.dataset_id=st.dataset_id AND s.stop_id=st.stop_id WHERE t.dataset_id=? AND t.route_id IN ('.or_in($routeIds).') GROUP BY t.trip_id,t.route_id,t.shape_id,t.headsign,t.direction_id ORDER BY d2 LIMIT 80';
    $q=$db->prepare($sql);$q->execute([$lat,$lon,$cos,or_active_date(),$ds,...$routeIds]);$tripRows=$q->fetchAll();if(!$tripRows)throw new RuntimeException('No active scheduled trips were found for bus '.trim($line).' today.');
    $selectedRoute=$tripRows[0]['route_id'];$byDir=[];foreach($tripRows as $r){if($r['route_id']!==$selectedRoute)continue;$dir=(string)$r['direction_id'];if(!isset($byDir[$dir]))$byDir[$dir]=$r;if(count($byDir)>=2)break;}
    $geoms=[];$stops=[];$nearestStop='';$nearestName='';$nearest=INF;$title='';
    foreach($byDir as $dir=>$r){$dirLabel=$dir==='1'?'inbound':'outbound';$tripStops=or_service_trip_stops($db,$ds,$r['trip_id'],$dirLabel);foreach($tripStops as $s){$stops[]=$s;$d=or_haversine($lat,$lon,$s['lat'],$s['lon']);if($d<$nearest){$nearest=$d;$nearestStop=$s['id'];$nearestName=$s['name'];}}$points=[];if((string)$r['shape_id']!==''){$sq=$db->prepare('SELECT point_lon,point_lat FROM or_shapes WHERE dataset_id=? AND shape_id=? ORDER BY point_sequence');$sq->execute([$ds,$r['shape_id']]);while($p=$sq->fetch())$points[]=[(float)$p['point_lon'],(float)$p['point_lat']];}if(count($points)<2){foreach($tripStops as $s)$points[]=[$s['lon'],$s['lat']];}$geoms[]=['direction'=>$dirLabel,'coordinates'=>$points];if($title===''&&trim((string)$r['headsign'])!=='')$title=(string)$r['headsign'];}
    $routeMeta=null;foreach($routeRows as $r)if($r['route_id']===$selectedRoute){$routeMeta=$r;break;}$label=$routeMeta&&trim((string)$routeMeta['short_name'])!==''?$routeMeta['short_name']:trim($line);$deps=$nearestStop!==''?or_service_timetable($db,$ds,$selectedRoute,$nearestStop,or_current_seconds()):[];
    return ['line'=>$label,'title'=>$title!==''?$title:('Bus '.$label),'source'=>'OpenRoad Transport Server · DfT BODS GTFS','coverage'=>'scheduled-route','geometries'=>$geoms,'stops'=>$stops,'timetable'=>['stopId'=>$nearestStop,'stopName'=>$nearestName!==''?$nearestName:'Nearby stop','departures'=>$deps,'source'=>'DfT BODS GTFS'],'liveAvailable'=>true];
}

function openroad_bus_stop(PDO $db,string $stopId,float $lat,float $lon): array {
    $region=openroad_region_for_point($lat,$lon);if($region===null||$region==='london')throw new RuntimeException('No prepared regional bus-stop timetable is available here.');$ds=openroad_region_dataset($db,$region);if(!$ds){openroad_enqueue_region($db,$region,'bus-stop');throw new RuntimeException('Transport data for this area is being prepared.');}openroad_region_touch($db,$region);
    $stop=null;if($stopId!==''){$q=$db->prepare('SELECT stop_id,stop_name,stop_lat,stop_lon FROM or_stops WHERE dataset_id=? AND stop_id=? LIMIT 1');$q->execute([$ds,$stopId]);$stop=$q->fetch();}
    if(!$stop){$near=or_nearby_stops($db,$ds,$lat,$lon,180,1);$stop=$near[0]??null;}if(!$stop)throw new RuntimeException('That bus stop could not be matched to the prepared timetable.');$sid=$stop['stop_id'];$now=or_current_seconds();$date=or_active_date();$services=[];
    // First list every active service that calls here today, even if its next bus is more than four hours away.
    $allSql='SELECT DISTINCT r.short_name,r.long_name,t.route_id,t.headsign FROM or_stop_times st JOIN or_trips t ON t.dataset_id=st.dataset_id AND t.trip_id=st.trip_id JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=? WHERE st.dataset_id=? AND st.stop_id=? ORDER BY r.short_name,t.headsign LIMIT 120';
    $q=$db->prepare($allSql);$q->execute([$date,$ds,$sid]);while($r=$q->fetch()){$line=trim((string)$r['short_name']);if($line==='')$line=trim((string)$r['long_name']);if($line==='')continue;$key=or_normalise_line($line).'|'.(string)$r['headsign'];$services[$key]=['line'=>$line,'destination'=>(string)$r['headsign'],'routeId'=>(string)$r['route_id'],'departures'=>[]];}
    // Then attach the next few departures without making the service list depend on the time window.
    $depSql='SELECT r.short_name,r.long_name,t.route_id,t.headsign,st.departure_sec FROM or_stop_times st JOIN or_trips t ON t.dataset_id=st.dataset_id AND t.trip_id=st.trip_id JOIN or_routes r ON r.dataset_id=t.dataset_id AND r.route_id=t.route_id JOIN or_service_dates sd ON sd.dataset_id=t.dataset_id AND sd.service_id=t.service_id AND sd.service_date=? WHERE st.dataset_id=? AND st.stop_id=? AND st.departure_sec BETWEEN ? AND ? ORDER BY st.departure_sec LIMIT 120';
    $q=$db->prepare($depSql);$q->execute([$date,$ds,$sid,$now-60,$now+6*3600]);while($r=$q->fetch()){$line=trim((string)$r['short_name']);if($line==='')$line=trim((string)$r['long_name']);if($line==='')continue;$key=or_normalise_line($line).'|'.(string)$r['headsign'];if(!isset($services[$key]))$services[$key]=['line'=>$line,'destination'=>(string)$r['headsign'],'routeId'=>(string)$r['route_id'],'departures'=>[]];if(count($services[$key]['departures'])<3)$services[$key]['departures'][]=or_clock((int)$r['departure_sec']);}
    $list=array_values($services);usort($list,function($a,$b){$at=$a['departures'][0]??'99:99';$bt=$b['departures'][0]??'99:99';$c=strcmp($at,$bt);if($c!==0)return $c;return strnatcasecmp((string)$a['line'],(string)$b['line']);});
    return ['stop'=>['id'=>$sid,'name'=>$stop['stop_name'],'lat'=>(float)$stop['stop_lat'],'lon'=>(float)$stop['stop_lon']],'services'=>$list,'source'=>'DfT BODS GTFS via OpenRoad server'];
}

