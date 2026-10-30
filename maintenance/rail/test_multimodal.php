<?php
declare(strict_types=1);
date_default_timezone_set('Europe/London');
require __DIR__.'/multimodal_planner.php';
function must(bool $condition,string $message):void{
    if(!$condition)throw new RuntimeException($message);
}
$now=(new DateTimeImmutable('tomorrow 08:00',new DateTimeZone('Europe/London')))->getTimestamp();
$from=['lat'=>51.435,'lon'=>-2.61];
$to=['lat'=>52.405,'lon'=>-1.514];
$makeBus=static function(array $a,array $b,int $earliest):array{
    $depart=$earliest+300;$arrive=$depart+900;
    $walk=or_mm_walk_leg($a,$b,'Start','Destination',$earliest,240);
    $p=or_mm_point($a);$q=or_mm_point($b);
    return ['source'=>'scheduled-bus','departure'=>$depart,'arrival'=>$arrive,
       'legs'=>[['mode'=>'bus','line'=>'X1','from'=>'Sample boarding',
                 'to'=>'Sample alighting','departure'=>date('H:i',$depart),
                 'arrival'=>date('H:i',$arrive),'departureEpoch'=>$depart,
                 'arrivalEpoch'=>$arrive,'fromLat'=>$a['lat'],'fromLon'=>$a['lon'],
                 'toLat'=>$b['lat'],'toLon'=>$b['lon'],'timeStatus'=>'scheduled',
                 'dataSource'=>'Synthetic test only']],
       'geometry'=>[['points'=>[$p,$q]]]];
};
$rail=['transitLegs'=>[
 ['mode'=>'foot'],
 ['mode'=>'train','fromCrs'=>'BRI','toCrs'=>'COV','departureEpoch'=>$now+3600,'arrivalEpoch'=>$now+9000],
 ['mode'=>'foot']
], 'legs'=>[
 ['points'=>[or_mm_point($from),or_mm_point($from)]],
 ['points'=>[or_mm_point($from),or_mm_point($to)]],
 ['points'=>[or_mm_point($to),or_mm_point($to)]]
],'summary'=>[],'clearRouteId'=>'rail-test'];
$start=$makeBus($from,$from,$now);$start['station']='BRI';
$end=$makeBus($to,$to,$now+9000+240);$end['station']='COV';
$good=or_mm_compose($rail,$from,$to,$start,$end,$now,300);
must(is_array($good),'Valid bus-train-bus journey rejected');
must(count($good['transitLegs'])===3,'Bus and train legs not concatenated');
must(count($good['legs'])===count($good['transitLegs']),'Transit leg geometry misaligned');
must(($good['clearRouteMultimodal']??false)===true,'Multimodal result flag absent');
must(($good['clearRouteDataStatus']??'')==='scheduled','Timetable incorrectly labelled live');
$late=$start;$late['arrival']=$now+3500;
must(or_mm_compose($rail,$from,$to,$late,$end,$now,300)===null,'Missed inbound train allowed');
$early=$end;$early['departure']=$now+9000+120;
must(or_mm_compose($rail,$from,$to,$start,$early,$now,300)===null,'Missed outbound bus allowed');
$wrong=$start;$wrong['station']='BTH';
must(or_mm_compose($rail,$from,$to,$wrong,$end,$now,300)===null,'Incorrect station connected');
$noBus=$start;$noBus['legs']=[];$noBus['geometry']=[];
$noBusEnd=['source'=>'foot','station'=>'COV','arrival'=>$now+9200,'legs'=>[],'geometry'=>[]];
must(or_mm_compose($rail,$from,$to,$noBus,$noBusEnd,$now,300)===null,'Busless result labelled multimodal');
echo "MULTIMODAL_TRANSFER_VALIDATION_OK\n";
$index=$argv[1]??'';
if($index!==''){
    $calls=0;
    $feeder=static function(PDO $db,array $a,array $b,int $earliest,int $window,float $speed)
              use (&$calls,$makeBus):array{
        $calls++;
        return $makeBus($a,$b,$earliest);
    };
    $db=new PDO('sqlite::memory:');
    $started=microtime(true);
    $result=or_mm_plan($db,$from['lat'],$from['lon'],$to['lat'],$to['lon'],
                     ['maxWalkMeters'=>900],$feeder,$now,$index);
    $elapsed=(int)round((microtime(true)-$started)*1000);
    must($calls<=6,'More than six bus lookup requests');
    must($elapsed<6000,'Rail-bus orchestration exceeded deadline');
    must(!empty($result['routes']),'No combined bus/train result on real national timetable');
    foreach($result['routes'] as $route){
        $modes=array_column($route['transitLegs'],'mode');
        must(in_array('bus',$modes,true)&&in_array('train',$modes,true),'Mixed result omitted a mode');
        must(count($route['legs'])===count($route['transitLegs']),'Mixed route geometry count mismatch');
    }
    echo "MULTIMODAL_REAL_TIMETABLE_SMOKE_OK ms=$elapsed bus_lookups=$calls routes=".count($result['routes'])."\n";
}
