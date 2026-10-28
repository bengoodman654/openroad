<?php
declare(strict_types=1);
/** OpenRoad calendar-only GTFS extension: never imports trips/stop times/shapes.
 * Must be executed from CLI inside existing private/bin/; no public endpoint.
 */
function or_calendar_days(string $first,string $last):array {
    $start=DateTimeImmutable::createFromFormat('!Y-m-d',$first);
    $end=DateTimeImmutable::createFromFormat('!Y-m-d',$last);
    if(!$start||!$end||$end<$start||$start->diff($end)->days>62)
        throw new RuntimeException('Invalid bounded calendar interval');
    $result=[];
    for($d=$start;$d<=$end;$d=$d->modify('+1 day'))
        $result[$d->format('Ymd')]=[$d->format('Y-m-d'),strtolower($d->format('l'))];
    return $result;
}
function or_calendar_csv(ZipArchive $archive,string $file,callable $callback):void{
    $stream=$archive->getStream($file);
    if(!$stream)throw new RuntimeException('Missing GTFS '.$file);
    try{
        $head=fgetcsv($stream);
        if(!is_array($head))throw new RuntimeException('Empty GTFS '.$file);
        $head=array_map(static fn($s)=>strtolower(trim(preg_replace('/^\xEF\xBB\xBF/','',(string)$s))),$head);
        $map=array_flip($head);
        $count=0;
        while(($row=fgetcsv($stream))!==false){
            if(++$count>150000)throw new RuntimeException('Unexpected calendar row limit');
            $value=static function(string $column)use($row,$map):string{
                $position=$map[$column]??null;
                return $position===null?'':trim((string)($row[$position]??''));
            };
            $callback($value);
        }
    }finally{fclose($stream);}
}
function or_calendar_expand(ZipArchive $zip,array $allowed,
                             string $first,string $last):array {
    $days=or_calendar_days($first,$last);
    $active=[];
    or_calendar_csv($zip,'calendar.txt',static function($value)use($days,$allowed,&$active){
        $service=$value('service_id');
        $a=$value('start_date');$b=$value('end_date');
        if(!isset($allowed[$service])||!preg_match('/^\d{8}$/D',$a)||
           !preg_match('/^\d{8}$/D',$b))return;
        foreach($days as $ymd=>[$date,$weekday]){
            if($ymd>=$a && $ymd<=$b && $value($weekday)==='1')
                $active[$ymd][$service]=true;
        }
    });
    or_calendar_csv($zip,'calendar_dates.txt',static function($value)use($days,$allowed,&$active){
        $ymd=$value('date');$service=$value('service_id');
        if(!isset($days[$ymd])||!isset($allowed[$service]))return;
        $type=$value('exception_type');
        if($type==='1')$active[$ymd][$service]=true;
        elseif($type==='2')unset($active[$ymd][$service]);
    });
    $rows=[];
    foreach($days as $ymd=>[$date,$weekday])
        foreach(array_keys($active[$ymd]??[]) as $service)
            $rows[]=[$service,$date];
    if(!$rows||count($rows)>60000)
        throw new RuntimeException('No valid or too many timetable calendar rows');
    return $rows;
}
function or_calendar_plan(PDO $db,string $region,string $zipPath,
                          DateTimeImmutable $today,int $daysAhead=45):array{
    if(!in_array($region,['south_west','west_midlands'],true))
        throw new RuntimeException('Unexpected region');
    if($daysAhead<14||$daysAhead>50)throw new RuntimeException('Horizon out of bounds');
    if(!is_file($zipPath)||is_link($zipPath)||filesize($zipPath)>500000000)
        throw new RuntimeException('Untrusted GTFS cache file');
    $age=time()-filemtime($zipPath);
    if($age<0||$age>60*86400)
        throw new RuntimeException('Cached source too old for a safe extension');
    $q=$db->prepare('SELECT dataset_id,updated_at FROM or_regions WHERE region_key=?');
    $q->execute([$region]);$regionRow=$q->fetch(PDO::FETCH_ASSOC);
    if(!$regionRow)throw new RuntimeException('Region not prepared');
    $ds=(int)$regionRow['dataset_id'];
    $q=$db->prepare('SELECT MAX(service_date) FROM or_service_dates WHERE dataset_id=?');
    $q->execute([$ds]);$last=$q->fetchColumn();
    if(!is_string($last)||!preg_match('/^\d{4}-\d{2}-\d{2}$/D',$last))
        throw new RuntimeException('No existing timetable coverage');
    $next=(new DateTimeImmutable($last))->modify('+1 day');
    $end=$today->modify('+'.$daysAhead.' days');
    $daysRemaining=(int)$today->diff(new DateTimeImmutable($last))->format('%r%a');
    if($next>$end)
        return ['outcome'=>'CURRENT','dataset'=>$ds,'last'=>$last,
                'daysRemaining'=>$daysRemaining,'rows'=>[]];
    if($next<$today->modify('-1 day'))
        throw new RuntimeException('Existing calendar has a gap; no silent backfill');
    $q=$db->prepare('SELECT DISTINCT service_id FROM or_trips WHERE dataset_id=?');
    $q->execute([$ds]);$allowed=[];
    while(($s=$q->fetchColumn())!==false){
        $allowed[(string)$s]=true;
        if(count($allowed)>40000)throw new RuntimeException('Unexpected service-ID count');
    }
    if(!$allowed)throw new RuntimeException('No existing trips');
    $zip=new ZipArchive();
    if($zip->open($zipPath)!==true)throw new RuntimeException('GTFS cache ZIP unreadable');
    try {$rows=or_calendar_expand($zip,$allowed,$next->format('Y-m-d'),$end->format('Y-m-d'));}
    finally{$zip->close();}
    return ['outcome'=>'EXTEND','dataset'=>$ds,'region'=>$region,
            'oldLast'=>$last,'newLast'=>$end->format('Y-m-d'),
            'rows'=>$rows,'daysRemaining'=>$daysRemaining];
}
function or_calendar_apply(PDO $db,array $plan):int {
    if(($plan['outcome']??null)!=='EXTEND')return 0;
    $ds=$plan['dataset'];$region=$plan['region'];$rows=$plan['rows'];
    if(!is_int($ds)||$ds<=0||!is_array($rows)||count($rows)>60000)
        throw new RuntimeException('Invalid calendar plan');
    $db->beginTransaction();
    try{
        // Detect another full GTFS importer switching datasets in parallel.
        $q=$db->prepare('SELECT dataset_id FROM or_regions WHERE region_key=? FOR UPDATE');
        $q->execute([$region]);
        if((int)$q->fetchColumn()!==$ds)
            throw new RuntimeException('Dataset changed during calendar build');
        foreach(array_chunk($rows,250) as $part){
            $values=implode(',',array_fill(0,count($part),'(?,?,?)'));
            $sql='INSERT IGNORE INTO or_service_dates (dataset_id,service_id,service_date) VALUES '.$values;
            $args=[];
            foreach($part as $row)array_push($args,$ds,$row[0],$row[1]);
            $db->prepare($sql)->execute($args);
        }
        $db->commit();
        return count($rows);
    }catch(Throwable $e){if($db->inTransaction())$db->rollBack();throw $e;}
}
