<?php
declare(strict_types=1);
date_default_timezone_set('Europe/London');
require __DIR__.'/rail_planner.php';
$index=$argv[1]??'';
if($index==='')exit(2);
$day=(new DateTimeImmutable('tomorrow 08:00',new DateTimeZone('Europe/London')))->getTimestamp();
$start=microtime(true);
$r=or_rail_plan(51.449,-2.58,52.4,-1.514,$index,$day);
$elapsed=round((microtime(true)-$start)*1000);
if(empty($r['routes']))throw new RuntimeException('Bristol to Coventry: no schedule found');
$first=$r['routes'][0];
$trains=array_values(array_filter($first['transitLegs'],static fn($l)=>($l['mode']??null)==='train'));
if(!$trains)throw new RuntimeException('Result contains no trains');
if(($first['clearRouteDataStatus']??null)!=='scheduled')throw new RuntimeException('False live claim');
foreach($trains as $train){
    if(empty($train['fromCrs'])||empty($train['toCrs'])||!isset($train['stops'][0]['lat']))
        throw new RuntimeException('Incomplete station or geometry');
}
if($elapsed>6000)throw new RuntimeException('Rail search exceeded safe time');
echo "RAIL_BRISTOL_COVENTRY_OK ms=$elapsed train_legs=".count($trains)." routes=".count($r['routes'])."\n";
// A daily on-demand planner must work during actual busy timetables, not
// only the quieter next-day test used in the initial prototype.
$today=(new DateTimeImmutable('today 08:00',new DateTimeZone('Europe/London')))->getTimestamp();
$start=microtime(true);
$todayRoutes=or_rail_plan(51.435,-2.61,52.405,-1.514,$index,$today);
$ms=round((microtime(true)-$start)*1000);
if(empty($todayRoutes['routes']))throw new RuntimeException('Busy-day Bristol to Coventry rail search returned no valid route');
if($ms>5000)throw new RuntimeException('Busy-day railway planner exceeded time budget');
echo "RAIL_BUSY_DAY_BRISTOL_COVENTRY_OK ms=$ms routes=".count($todayRoutes['routes'])."\n";
