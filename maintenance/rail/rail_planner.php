<?php
declare(strict_types=1);
/** OpenRoad read-only rail routing, no network/filesystem writes during requests. */
function or_rail_km(float $a,float $b,float $c,float $d):float{
    $x=deg2rad($c-$a);$y=deg2rad($d-$b);
    return 12742*asin(min(1.0,sqrt(sin($x/2)**2+cos(deg2rad($a))*cos(deg2rad($c))*sin($y/2)**2)));
}
function or_rail_index(string $root):array{
    if(!is_file($root.'/manifest.json')||!is_file($root.'/stations.json'))throw new RuntimeException('No indexed rail timetable');
    if(filesize($root.'/stations.json')>800000||filesize($root.'/manifest.json')>10000)throw new RuntimeException('Invalid rail index');
    $meta=json_decode((string)file_get_contents($root.'/manifest.json'),true);
    $stations=json_decode((string)file_get_contents($root.'/stations.json'),true);
    if(!is_array($meta)||($meta['version']??null)!==2||!is_array($stations)||count($stations)<1000||!is_file($root.'/events.sqlite'))throw new RuntimeException('Invalid rail timetable');
    $day=(new DateTimeImmutable('today',new DateTimeZone('Europe/London')))->format('Y-m-d');
    if(($meta['from']??'~')>$day||($meta['through']??'')<$day)throw new RuntimeException('Rail timetable expired');
    return [$meta,$stations];
}
function or_rail_near(array $stations,float $lat,float $lon,int $limit):array{
    $near=[];
    foreach($stations as $code=>$s){
        if(!preg_match('/^[A-Z]{3}$/D',(string)$code)||!is_array($s)||count($s)<3)continue;
        $d=or_rail_km($lat,$lon,(float)$s[1],(float)$s[2])*1000;
        $walk=(int)ceil($d*1.25/1.25);
        if($walk>3000)continue;
        $near[]=['station'=>(string)$code,'walk'=>$walk,'metres'=>$d];
    }
    usort($near,static fn($a,$b)=>$a['walk']<=>$b['walk']);
    return array_slice($near,0,$limit);
}
function or_rail_departures(string $root,string $code,int $start,int $end):array{
    static $conn=null,$query=null,$rootPath='';
    if($rootPath!==$root){
        $file=$root.'/events.sqlite';
        if(!is_file($file)||filesize($file)>100000000)throw new RuntimeException('Invalid rail timetable file');
        $conn=new PDO('sqlite:file:'.$file.'?mode=ro');
        $conn->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
        $conn->exec('PRAGMA query_only=ON');
        $conn->exec('PRAGMA busy_timeout=150');
        $query=$conn->prepare('SELECT dep,arr,d,trip,line FROM events WHERE o=? AND dep>=? AND dep<=? ORDER BY dep LIMIT 150');
        $rootPath=$root;
    }
    $query->execute([$code,$start,$end]);
    $out=[];
    while($row=$query->fetch(PDO::FETCH_NUM)){
        $out[]=[(int)$row[0],(int)$row[1],(string)$row[2],(string)$row[3],(string)$row[4],''];
    }
    $query->closeCursor();
    return $out;
}
function or_rail_format(array $edges,array $stations,float $a,float $b,float $c,float $d,int $now,int $walkIn,int $walkOut):array{
    $first=$edges[0];$last=$edges[count($edges)-1];
    $from=$stations[$first[2]];$to=$stations[$last[3]];
    $groups=[];
    foreach($edges as $e){
        $n=count($groups);
        if($n&&$groups[$n-1]['trip']===$e[4]&&$groups[$n-1]['to']===$e[2]){
            $groups[$n-1]['to']=$e[3];$groups[$n-1]['arr']=$e[1];$groups[$n-1]['stops'][]=$e[3];
        }else $groups[]=['dep'=>$e[0],'arr'=>$e[1],'from'=>$e[2],'to'=>$e[3],'trip'=>$e[4],
                          'line'=>$e[5],'stops'=>[$e[2],$e[3]]];
    }
    $legs=[['mode'=>'foot','from'=>'My location','to'=>$from[0],'durationSeconds'=>$walkIn,
            'departure'=>date('H:i',$now),'arrival'=>date('H:i',$now+$walkIn),
            'timeStatus'=>'scheduled','geometryStatus'=>'loading']];
    $geom = [ ['points' => [ ['latitude'=>$a,'longitude'=>$b], ['latitude'=>(float)$from[1],'longitude'=>(float)$from[2]] ] ] ];
    foreach($groups as $g){
        $stops=[];$coords=[];
        foreach($g['stops'] as $code){
            $s=$stations[$code];$stops[]=['id'=>$code,'name'=>$s[0],'lat'=>(float)$s[1],'lon'=>(float)$s[2]];
            $coords[]=['latitude'=>(float)$s[1],'longitude'=>(float)$s[2]];
        }
        $u=$stations[$g['from']];$v=$stations[$g['to']];
        $legs[]=['mode'=>'train','line'=>$g['line']==='Train'?'':$g['line'],
                 'from'=>$u[0],'to'=>$v[0],'fromCrs'=>$g['from'],'toCrs'=>$g['to'],
                 'fromLat'=>(float)$u[1],'fromLon'=>(float)$u[2],'toLat'=>(float)$v[1],'toLon'=>(float)$v[2],
                 'departure'=>date('H:i',$g['dep']),'arrival'=>date('H:i',$g['arr']),
                 'durationSeconds'=>$g['arr']-$g['dep'],'timeStatus'=>'scheduled',
                 'dataSource'=>'GB Transit scheduled rail timetable','stops'=>$stops,'stopCount'=>count($stops)-2];
        $geom[]=['points'=>$coords];
    }
    $legs[]=['mode'=>'foot','from'=>$to[0],'to'=>'Destination','durationSeconds'=>$walkOut,
             'departure'=>date('H:i',$last[1]),'arrival'=>date('H:i',$last[1]+$walkOut),
             'timeStatus'=>'scheduled','geometryStatus'=>'loading'];
    $geom[]=['points'=>[['latitude'=>(float)$to[1],'longitude'=>(float)$to[2]],['latitude'=>$c,'longitude'=>$d]]];
    $id=substr(hash('sha256',implode('|',array_map(static fn($g)=>$g['trip'],$groups)).'|'.$first[0]),0,24);
    return ['clearRouteTransit'=>true,'clearRouteId'=>'rail-'.$id,
            'summary'=>['travelTimeInSeconds'=>$last[1]+$walkOut-$now,'lengthInMeters'=>0],
            'clearRouteDeparture'=>date('H:i',$first[0]),'clearRouteArrival'=>date('H:i',$last[1]+$walkOut),
            'clearRouteDataStatus'=>'scheduled','clearRouteDataSource'=>'GB Transit rail timetable',
            'clearRouteWarning'=>'Scheduled trains only. Check live updates before travelling; walking times are estimates.',
            'transitLegs'=>$legs,'legs'=>$geom,'guidance'=>['instructions'=>[]]];
}
/** Bounded earliest-arrival search: same train has no transfer penalty; changes require 7 minutes. */
function or_rail_plan(float $a,float $b,float $c,float $d,?string $root=null,?int $now=null,array $options=[]):array{
    $root=$root??dirname(__DIR__).'/cache/rail-routing/current';
    [$meta,$stations]=or_rail_index($root);
    $now=$now??time();
    $start=$options['starts']??or_rail_near($stations,$a,$b,5);
    $end=$options['ends']??or_rail_near($stations,$c,$d,6);
    $resultLimit=max(1,min(20,(int)($options['limit']??3)));
    if(!$start||!$end)return ['routes'=>[],'source'=>'rail','coverage'=>'no_nearby_station'];
    $targets=[];foreach($end as $e){
        if(isset($e['station'],$stations[$e['station']])&&isset($e['walk'])&&is_numeric($e['walk']))$targets[$e['station']]=$e;
    }
    if(!$targets)return ['routes'=>[],'source'=>'rail','coverage'=>'no_destination_station'];
    $queue=new SplPriorityQueue();$queue->setExtractFlags(SplPriorityQueue::EXTR_DATA);
    foreach($start as $s){
        if(!isset($s['station'],$stations[$s['station']])||!isset($s['walk'])||!is_numeric($s['walk']))continue;
        $ready=(int)($s['ready']??($now+$s['walk']));
        if($ready<$now || $ready>$now+7200)continue;
        $queue->insert(['at'=>$ready,'code'=>$s['station'],'trip'=>'','changes'=>-1,
                        'edges'=>[],'walk'=>$s['walk']],-($ready+(int)(or_rail_km((float)$stations[$s['station']][1],(float)$stations[$s['station']][2],$c,$d)*32)));
    }
    if($queue->isEmpty())return ['routes'=>[],'source'=>'rail','coverage'=>'no_reachable_origin_station'];
    $best=[];$routes=[];$expanded=0;$deadline=microtime(true)+4.0;
    $goalCost=static function(string $station)use($stations,$c,$d):int{
        $p=$stations[$station];
        // Geographic guidance only: queue priority, not the journey's actual score.
        return (int)round(or_rail_km((float)$p[1],(float)$p[2],$c,$d)*32);
    };
    while(!$queue->isEmpty()&&$expanded++<650&&microtime(true)<$deadline){
        $s=$queue->extract();
        if($s['at']>$now+8*3600)continue;
        if(isset($targets[$s['code']])&&$s['edges']){
            $r=or_rail_format($s['edges'],$stations,$a,$b,$c,$d,$now,$s['walk'],$targets[$s['code']]['walk']);
            $routes[$r['clearRouteId']]=$r;
            if(count($routes)>=max(10,$resultLimit))break;
        }
        foreach(or_rail_departures($root,$s['code'],$s['at'],$now+6*3600) as $e){
            [$dep,$arr,$dest,$trip,$line,$head]=$e;
            if(!isset($stations[$dest]))continue;
            $same=$s['trip']!==''&&$s['trip']===$trip;
            $extra=$s['trip']!==''&&!$same?420:0;
            if($dep<$s['at']+$extra)continue;
            $changes=$s['changes']+($same?0:1);
            if($changes>2)continue;
            $key=$dest.'|'.$trip.'|'.$changes.'|'.intdiv((int)$arr,180);
            if(isset($best[$key])&&$best[$key]<=$arr)continue;
            $best[$key]=$arr;
            $edges=$s['edges'];$edges[]=[(int)$dep,(int)$arr,$s['code'],(string)$dest,(string)$trip,(string)$line];
            if(count($edges)>50)continue;
            $queue->insert(['at'=>(int)$arr,'code'=>$dest,'trip'=>$trip,'changes'=>$changes,
                            'edges'=>$edges,'walk'=>$s['walk']],-((int)$arr+$goalCost($dest)));
        }
    }
    if(PHP_SAPI==='cli'&&getenv('OPENROAD_RAIL_DEBUG')==='1')
        fwrite(STDERR,"RAIL_DEBUG expanded=$expanded candidates=".count($routes)."\n");
    $items=array_values($routes);
    usort($items,static fn($a,$b)=>$a['summary']['travelTimeInSeconds']<=>$b['summary']['travelTimeInSeconds']);
    return ['routes'=>array_slice($items,0,$resultLimit),'source'=>'rail','coverage'=>'scheduled',
            'calendarThrough'=>$meta['through']];
}
