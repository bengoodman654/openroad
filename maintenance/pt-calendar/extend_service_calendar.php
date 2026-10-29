<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
require_once dirname(__DIR__).'/lib/calendar_extension.php';
$region=$argv[1]??'south_west';
$execute=in_array('--apply',$argv,true);
$cache=openroad_private_root().'/cache';
$lock=fopen($cache.'/update.lock','c+');
if(!$lock||!flock($lock,LOCK_EX|LOCK_NB)){fwrite(STDERR,"Calendar lock unavailable\n");exit(3);}
try{
    $db=openroad_db();
    try{$db->exec('SET SESSION max_statement_time=3');}
    catch(Throwable $dbLimitUnsupported){
        try{$db->exec('SET SESSION max_execution_time=3000');}
        catch(Throwable $dbLimitUnavailable){}
    }
    $today=new DateTimeImmutable('today');
    $source=$cache.'/'.$region.'_gtfs.zip';
    $plan=or_calendar_plan($db,$region,$source,$today,45);
    if($plan['outcome']==='CURRENT'){
        echo "CALENDAR_CURRENT days_left=".$plan['daysRemaining']."\n";exit(0);
    }
    echo "CALENDAR_PLAN rows=".count($plan['rows']).
         " old_last=".$plan['oldLast']." new_last=".$plan['newLast'].
         " source_age_days=".(int)((time()-filemtime($source))/86400)."\n";
    if(!$execute){echo "DRY_RUN_ONLY\n";exit(0);}
    $n=or_calendar_apply($db,$plan);
    echo "CALENDAR_EXTENDED rows_attempted=".$n." until=".$plan['newLast'].
         " provenance=cached_feed_schedule_only\n";
}catch(Throwable $e){
    fwrite(STDERR,"CALENDAR_FAILED class=".get_class($e).
         " reason=".preg_replace('/[^a-zA-Z0-9 _.-]/','',substr($e->getMessage(),0,120))."\n");
    exit(2);
}finally{flock($lock,LOCK_UN);fclose($lock);}
