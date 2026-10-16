<?php
require_once __DIR__.'/../private/lib/router.php';
class FakeDb extends PDO { public function __construct() {} }
function check(bool $ok, string $message): void { if(!$ok) throw new Exception($message); }
$fake = new FakeDb();
function rejected(FakeDb $fake, array $loc, string $expect): void {
    try { or_dataset_for_points($fake, ...$loc); throw new Exception('Missing expected rejection'); }
    catch(RuntimeException $e) { check(str_contains($e->getMessage(),$expect),$e->getMessage()); }
}
rejected($fake,[51.455,-2.589,51.515,-0.127], 'national rail');
rejected($fake,[51.455,-2.589,52.48,-1.89], 'different regions');
rejected($fake,[51.455,-2.589,55.953,-3.188], 'outside');
or_route_deadline(microtime(true)-1);
try { or_route_check_budget(); throw new Exception('Budget guard failed'); }
catch(RuntimeException $e) {check(str_contains($e->getMessage(),'time budget'),'unexpected budget error');}
or_route_deadline(microtime(true)+1);
or_route_check_budget();
check(or_route_elapsed_ms(microtime(true)-0.1)>=95,'elapsed time');
// Ensure journey logs contain only aggregate diagnostics.
openroad_route_perf_log('fast','ok','hit',microtime(true)-0.02,3);
$log=file_get_contents(__DIR__.'/../private/logs/journey-timings.jsonl');
$row=json_decode(trim(explode("\n",trim($log))[0]),true);
check($row['phase']==='fast'&&$row['routes']===3,'log fields');
check(!isset($row['latitude'])&&!isset($row['device'])&&!isset($row['apikey']),'private info');
@unlink(__DIR__.'/../private/logs/journey-timings.jsonl');
echo "Router fast-fail, query budget and privacy diagnostics: passed\n";
