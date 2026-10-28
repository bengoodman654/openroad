<?php
declare(strict_types=1);
/**
 * RESEARCH ENDPOINT: emitted only into an isolated staged server ZIP.
 * Never installed under live public/api/v2. Requires paired-device signatures,
 * an existing prebuilt dataset and a private, explicitly configured secret.
 */
$private=dirname($_SERVER['DOCUMENT_ROOT'],2).'/openroad-private';
if(!is_file($private.'/lib/auth.php')||
   !is_file($private.'/lib/php_v2_protocol.php')){
    http_response_code(404);exit;
}
require_once $private.'/lib/router.php';
require_once $private.'/lib/auth.php';
require_once $private.'/lib/php_v2_protocol.php';
try{
    $body=openroad_require_post_json();
    $db=openroad_db();
    $verified=openroad_require_signed($db,$body);
    $request=json_decode($body,true,12,JSON_THROW_ON_ERROR);
    if(!is_array($request))
        throw new InvalidArgumentException('Invalid v2 request');
    $secretsPath=openroad_private_root().'/provider-secrets.php';
    $secrets=is_file($secretsPath)?require $secretsPath:null;
    $secret=is_array($secrets)?($secrets['pt_v2_hmac_secret']??null):null;
    if(!is_string($secret)||strlen($secret)<32)
        openroad_json(['outcome'=>'PROVIDER_UNAVAILABLE',
            'reasonCode'=>'PT_V2_NOT_CONFIGURED','researchOnly'=>true],503);
    $directory=openroad_private_root().'/cache/pt-v2-jobs';
    if(!is_dir($directory)&&!@mkdir($directory,0700,true)&&!is_dir($directory))
        throw new RuntimeException('Research task store unavailable');
    $registry=new OpenRoadV2ResearchCancellation($directory,$secret,2,128);
    $choose=static function(array $query)use($db):string {
        [$dataset,$region]=or_dataset_for_points(
            $db,$query['from']['lat'],$query['from']['lon'],
            $query['to']['lat'],$query['to']['lon']);
        if(!is_int($dataset)&&!ctype_digit((string)$dataset))
            throw new RuntimeException('No prepared dataset');
        return ptv2_snapshot_id((string)$region.':'.(string)$dataset);
    };
    $planner=static function(array $query,callable $cancelCheck)use($db):array {
        $from=$query['from'];$to=$query['to'];
        return openroad_plan_bus(
            $db,$from['lat'],$from['lon'],$to['lat'],$to['lon'],
            $query['settings'],$cancelCheck);
    };
    $reply=ptv2_dispatch($verified,$request,$registry,
                         $choose,$planner,static fn():int=>time());
    $status=200;
    if(in_array($reply['outcome'],['INPUT_INVALID'],true))$status=400;
    elseif(in_array($reply['outcome'],['COVERAGE_MISSING'],true))$status=409;
    elseif(in_array($reply['outcome'],['RATE_LIMITED'],true))$status=429;
    elseif(in_array($reply['outcome'],['PROVIDER_UNAVAILABLE'],true))$status=503;
    openroad_json($reply,$status);
}catch(InvalidArgumentException $e){
    openroad_json(['outcome'=>'INPUT_INVALID','reasonCode'=>'BAD_REQUEST',
                   'researchOnly'=>true],400);
}catch(Throwable $e){
    openroad_log_error($e);
    openroad_json(['outcome'=>'PROVIDER_UNAVAILABLE',
                   'reasonCode'=>'PT_V2_UNAVAILABLE',
                   'researchOnly'=>true],503);
}
