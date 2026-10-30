<?php
declare(strict_types=1);
define('OPENROAD_TRAIN_LIVE_TEST',true);
require __DIR__.'/rail_train_live.php';
function ensure(bool $x,string $msg):void{if(!$x)throw new RuntimeException($msg);}
$epoch=(new DateTimeImmutable('tomorrow 10:22',new DateTimeZone('Europe/London')))->getTimestamp();
$mock=[
 ['std'=>'10:22','etd'=>'10:32','platform'=>'4','destination'=>'Birmingham New Street','cancelled'=>false,'serviceID'=>'A'],
 ['std'=>'10:24','etd'=>'On time','platform'=>'2','destination'=>'London Paddington','cancelled'=>false],
];
$m=or_train_match_live($mock,'BRI','BHM',$epoch,'Birmingham New Street');
ensure($m['matched']===true,'Could not match unique scheduled departure');
ensure($m['delayMinutes']===10,'Delay arithmetic wrong');
ensure($m['platform']==='4','Platform lost');
ensure(or_train_match_live([$mock[0],$mock[0]],'BRI','BHM',$epoch)['status']==='ambiguous','Collision must be rejected');
$similar=$mock[0];$similar['destination']='London Paddington';$similar['callingCrs']=['RDG','PAD'];
$mock[0]['callingCrs']=['BTH','BHM'];
$reliable=or_train_match_live([$mock[0],$similar],'BRI','BHM',$epoch);
ensure($reliable['matched']===true && $reliable['platform']==='4',
    'Calling points should distinguish same-minute departures without guessing');
ensure(or_train_match_live([], 'BRI','BHM',$epoch)['status']==='not_listed','Missing train must not be fabricated');
$blocked=or_train_live_lookup('BRI','BHM',$epoch,'',static function(){throw new RuntimeException('Must not fetch');},$epoch-15000);
ensure($blocked['status']==='not_yet','Too-early live lookup must not consume provider quota');
$called=0;
$live=or_train_live_lookup('BRI','BHM',$epoch,'Birmingham New Street',
    static function(...$args)use($mock,&$called){$called++;return [200,['services'=>$mock,'checkedAt'=>'2026-10-30T10:00:00Z']];},$epoch-1800);
ensure($called===1&&$live['matched']===true,'Live board should only fetch once');
echo "TRAIN_LIVE_MATCHING_OK\n";
