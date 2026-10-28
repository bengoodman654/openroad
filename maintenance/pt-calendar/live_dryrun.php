<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'||count($argv)!==3){fwrite(STDERR,"CLI_REQUIRED\n");exit(2);}
require_once $argv[1].'/lib/bootstrap.php';
require_once $argv[2];
try {
    $db=openroad_db();
    $db->exec('SET SESSION max_statement_time=3');
    $plan=or_calendar_plan($db,'south_west',
        $argv[1].'/cache/south_west_gtfs.zip',
        new DateTimeImmutable('today'),45);
    echo "CALENDAR_DRYRUN outcome=".$plan['outcome'].
        " dataset=".$plan['dataset'].
        " proposed_rows=".count($plan['rows']).
        " old_last=".($plan['oldLast']??$plan['last']).
        " new_last=".($plan['newLast']??$plan['last'])."\n";
}catch(Throwable $e){
    fwrite(STDERR,"CALENDAR_DRYRUN_ERROR reason=".
        preg_replace('/[^a-zA-Z0-9 ._-]/','',substr($e->getMessage(),0,100))."\n");
    exit(3);
}
