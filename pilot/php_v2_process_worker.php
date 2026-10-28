<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_route_worker.php';
if(PHP_SAPI!=='cli'||count($argv)!==8)exit(50);
[$script,$dir,$key,$token,$device,$flag,$out,$delay]=$argv;
$reg=new OpenRoadV2ResearchCancellation($dir,$key,2,20);
usleep(max(0,min(500,(int)$delay))*1000);
$clock=static fn():int=>time();
$response=ptv2_run_authenticated_task(
    $reg,['deviceId'=>$device],$token,
    static function($check)use($flag){
        file_put_contents($flag,'REGISTERED');
        for($i=0;$i<60;$i++){
            if($check())return [['mustNotPublish'=>true]];
            usleep(20000);
        }
        return [['research'=>'synthetic-only']];
    },$clock
);
file_put_contents($out,json_encode($response,JSON_THROW_ON_ERROR));
