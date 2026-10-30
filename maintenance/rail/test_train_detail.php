<?php
declare(strict_types=1);
require __DIR__.'/rail_train_detail.php';
$root=$argv[1]??'';
if($root==='')exit(2);
$db=new PDO('sqlite:file:'.$root.'/events.sqlite?mode=ro');
$q=$db->query("SELECT trip,o,d,dep FROM events WHERE o='BRI' AND d<>'BRI' ORDER BY dep LIMIT 40");
$ok=false;
while($row=$q->fetch(PDO::FETCH_ASSOC)){
    try{
        $detail=or_train_detail($root,(int)$row['trip'],$row['o'],$row['d'],(int)$row['dep']);
        if(count($detail['calls'])<2)continue;
        if(in_array($detail['geometryStatus'],['schematic','track_aligned','partly_track_aligned'],true) && count($detail['routePoints'])>=2){$ok=true;break;}
    }catch(Throwable $e){continue;}
}
if(!$ok)throw new RuntimeException('Could not find a scheduled Bristol train with usable shape and calling points');
if(($detail['calls'][0]['scheduledDeparture']??null)==='')throw new RuntimeException('Scheduled timetable is empty');
if(count($detail['routePoints'])>2400)throw new RuntimeException('Rail shape unexpectedly large');
echo 'RAIL_TRAIN_DETAIL_OK trip='.$detail['tripId'].' calls='.count($detail['calls']).' points='.count($detail['routePoints'])."\n";
try{or_train_detail($root,(int)$row['trip'],'ZZZ',$row['d'],(int)$row['dep']);throw new RuntimeException('Invalid station accepted');}
catch(RuntimeException $e){if($e->getMessage()==='Invalid station accepted')throw $e;}
