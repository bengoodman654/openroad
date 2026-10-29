<?php
declare(strict_types=1);
require_once __DIR__.'/php_v2_python_process.php';

function must(bool $x,string $label):void{
    if(!$x)throw new RuntimeException('FAILED '.$label);
    echo "PASS ".$label."\n";
}
function rejected(callable $job,string $label):void{
    try{$job();}
    catch(RuntimeException $e){must(true,$label);return;}
    throw new RuntimeException('Expected rejection: '.$label);
}
$python=trim((string)shell_exec('command -v python3'));
if($python===''||!is_executable($python))throw new RuntimeException('Python unavailable in test');
$root=sys_get_temp_dir().'/or-python-worker-'.bin2hex(random_bytes(8));
mkdir($root,0700);
$script="$root/worker.py";$index="$root/index.sqlite";
file_put_contents($index,'fixture index placeholder');
$sha=str_repeat('a',64);
$q=['from'=>['lat'=>51.44,'lon'=>-2.60],
    'to'=>['lat'=>51.45,'lon'=>-2.61],
    'settings'=>['maxWalk'=>10,'walkSpeed'=>'normal']];
$opts=['python'=>$python,'script'=>$script,'index'=>$index,
       'region'=>'south_west','sourceSha256'=>$sha,
       'serviceDate'=>'2026-10-29','earliestSec'=>9*3600];
$never=static fn():bool=>false;
try{
    file_put_contents($script,
        "import json,sys\n".
        "data=json.load(sys.stdin)\n".
        "sha=sys.argv[sys.argv.index('--source-sha')+1]\n".
        "print(json.dumps({'outcome':'OK','researchOnly':True,".
        "'results':[{'selectable':False,'sourceArchiveSha256':sha}]}))\n");
    $reply=ptv2_run_city_process($q,$never,$opts);
    must($reply['outcome']==='OK'&&count($reply['results'])===1,
         'verified source route delivered as research-only');
    $cache="$root/city.json.gz";
    file_put_contents($cache,'fixture cached package placeholder');
    $cacheMode=[...$opts,'index'=>'',
                'snapshotCache'=>$cache,
                'packageSha256'=>str_repeat('b',64)];
    $cached=ptv2_run_city_process($q,$never,$cacheMode);
    must($cached['outcome']==='OK',
         'bounded process accepts protected compressed city snapshots');
    $badCache=[...$cacheMode,'packageSha256'=>'bad'];
    rejected(static fn()=>ptv2_run_city_process($q,$never,$badCache),
             'uncertified city-cache checksum rejected before worker launch');

    file_put_contents($script,
        "import json\n".
        "print(json.dumps({'outcome':'OK','researchOnly':True,".
        "'results':[{'selectable':True,'sourceArchiveSha256':'".
        $sha."'}]}))\n");
    rejected(static fn()=>ptv2_run_city_process($q,$never,$opts),
             'Python cannot make an unverified route selectable');

    $slowScript="import time\n".
                "time.sleep(5)\n".
                "print('{\"outcome\":\"OK\",\"researchOnly\":true,\"results\":[]}')\n";
    file_put_contents($script,$slowScript);
    $started=microtime(true);
    $cancel=static fn():bool=>(microtime(true)-$started)>=0.12;
    rejected(static fn()=>ptv2_run_city_process($q,$cancel,$opts),
             'cancel request terminates running Python process');
    must(microtime(true)-$started<2.0,
         'cancellation releases the process promptly');

    $started=microtime(true);
    rejected(static fn()=>ptv2_run_city_process($q,$never,$opts,2),
             'worker deadline kills long-running Python');
    must(microtime(true)-$started<3.5,'worker deadline is bounded');

    $bad=[...$opts,'sourceSha256'=>'invalid'];
    rejected(static fn()=>ptv2_run_city_process($q,$never,$bad),
             'source SHA must be exactly expected form');

    echo "OpenRoad PHP->Python private worker limits: ALL TESTS PASSED\n";
}finally{
    foreach(glob($root.'/*')?:[] as $file)unlink($file);
    rmdir($root);
}
