<?php
function openroad_private_root(): string { return dirname(__DIR__); }
function openroad_config(): array {
    static $cfg = null;
    if ($cfg !== null) return $cfg;
    $cfg = require openroad_private_root() . '/config.php';
    if (!is_array($cfg)) throw new RuntimeException('OpenRoad config could not be loaded.');
    date_default_timezone_set($cfg['timezone'] ?? 'Europe/London');
    return $cfg;
}
function openroad_db(): PDO {
    static $pdo = null;
    if ($pdo instanceof PDO) return $pdo;
    $c = openroad_config();
    $dsn = 'mysql:host=' . $c['db_host'] . ';dbname=' . $c['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $c['db_user'], $c['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => true,
    ]);
    return $pdo;
}
function openroad_security_headers(): void {
    header('Cache-Control: no-store, max-age=0');
    header('Pragma: no-cache');
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: no-referrer');
    header("Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'");
    header('X-Robots-Tag: noindex, nofollow, noarchive');
}
function openroad_json(array $payload, int $status=200): void {
    http_response_code($status);
    openroad_security_headers();
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}
function openroad_not_found(): void { http_response_code(404); openroad_security_headers(); exit; }
function openroad_require_post_json(): string {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') openroad_not_found();
    $len = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($len > 65536) openroad_json(['ok'=>false,'error'=>'Request too large'],413);
    $body = file_get_contents('php://input');
    if ($body === false) $body = '';
    return $body;
}
function openroad_schema(PDO $db): void {
    $sql = file_get_contents(openroad_private_root() . '/schema.sql');
    if ($sql === false) throw new RuntimeException('schema.sql is missing');
    foreach (preg_split('/;\s*(?:\r?\n|$)/', $sql) as $statement) {
        $statement = trim($statement);
        if ($statement !== '') $db->exec($statement);
    }
}
function openroad_current_dataset(PDO $db): int {
    $stmt=$db->query("SELECT meta_value FROM or_meta WHERE meta_key='current_dataset' LIMIT 1");
    $v=$stmt ? $stmt->fetchColumn() : false;
    return $v===false ? 0 : (int)$v;
}
function openroad_meta(PDO $db, string $key, ?string $default=null): ?string {
    $stmt=$db->prepare('SELECT meta_value FROM or_meta WHERE meta_key=? LIMIT 1');
    $stmt->execute([$key]);
    $v=$stmt->fetchColumn();
    return $v===false ? $default : (string)$v;
}
function openroad_setting(PDO $db, string $key, ?string $default=null): ?string {
    $stmt=$db->prepare('SELECT setting_value FROM or_settings WHERE setting_key=? LIMIT 1');
    $stmt->execute([$key]);
    $v=$stmt->fetchColumn();
    return $v===false ? $default : (string)$v;
}
function openroad_set_setting(PDO $db, string $key, string $value): void {
    $q=$db->prepare('INSERT INTO or_settings(setting_key,setting_value) VALUES(?,?) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)');
    $q->execute([$key,$value]);
}
/** Single-line privacy-preserving timing events for server-side bottleneck analysis. */
function openroad_route_perf_log(string $phase,string $outcome,string $cache,float $started,int $routeCount): void {
    try {
        $dir=openroad_private_root().'/logs';
        if (!is_dir($dir)) @mkdir($dir,0750,true);
        $row=['time'=>date(DATE_ATOM),'event'=>'journey','phase'=>$phase==='fast'?'fast':'full',
              'outcome'=>$outcome,'cache'=>$cache==='hit'?'hit':'miss',
              'ms'=>(int)round((microtime(true)-$started)*1000),'routes'=>$routeCount];
        @file_put_contents($dir.'/journey-timings.jsonl',json_encode($row,JSON_UNESCAPED_SLASHES).PHP_EOL,FILE_APPEND|LOCK_EX);
    } catch(Throwable $ignored) {}
}
function openroad_log_error(Throwable $e): void {
    try {
        $dir=openroad_private_root().'/logs';
        if(!is_dir($dir)) @mkdir($dir,0750,true);
        $line='['.date(DATE_ATOM).'] '.get_class($e).': '.$e->getMessage().PHP_EOL;
        @file_put_contents($dir.'/server-error.log',$line,FILE_APPEND|LOCK_EX);
    } catch(Throwable $ignored) {}
}
function openroad_server_secret(): string {
    static $secret = null;
    if ($secret !== null) return $secret;
    $path=openroad_private_root().'/cache/server_secret.bin';
    $dir=dirname($path);
    if(!is_dir($dir) && !mkdir($dir,0750,true)) throw new RuntimeException('Could not create private cache directory.');
    if(is_file($path)) {
        $data=file_get_contents($path);
        if($data!==false && strlen($data)>=32) return $secret=$data;
    }
    $data=random_bytes(32);
    if(file_put_contents($path,$data,LOCK_EX)===false) throw new RuntimeException('Could not create server secret.');
    @chmod($path,0600);
    return $secret=$data;
}

function openroad_regions(): array {
    static $regions=null;if($regions!==null)return $regions;
    $cfg=openroad_config();$regions=is_array($cfg['regions']??null)?$cfg['regions']:[];
    $catalog=openroad_private_root().'/regions.php';
    if(is_file($catalog)){$extra=require $catalog;if(is_array($extra))$regions=array_replace($extra,$regions);}
    return $regions;
}
function openroad_region_config(string $key): ?array {
    $regions=openroad_regions();
    return isset($regions[$key]) && is_array($regions[$key]) ? $regions[$key] : null;
}
function openroad_region_for_point(float $lat,float $lon): ?string {
    // London is routed directly by TfL in the Android app; do not prepare a duplicate server copy.
    if($lat>=51.20&&$lat<=51.75&&$lon>=-0.62&&$lon<=0.20)return 'london';
    foreach(openroad_regions() as $key=>$r){
        $b=$r['bbox']??null;if(!is_array($b)||count($b)<4)continue;
        if($lat>=(float)$b[0]&&$lat<=(float)$b[2]&&$lon>=(float)$b[1]&&$lon<=(float)$b[3])return (string)$key;
    }
    return null;
}
function openroad_region_dataset(PDO $db,string $region): int {
    $q=$db->prepare('SELECT dataset_id FROM or_regions WHERE region_key=? LIMIT 1');$q->execute([$region]);$v=$q->fetchColumn();return $v===false?0:(int)$v;
}
function openroad_region_touch(PDO $db,string $region): void {
    $q=$db->prepare('UPDATE or_regions SET last_used_at=NOW() WHERE region_key=?');$q->execute([$region]);
}
function openroad_region_status(PDO $db): array {
    $out=[];$q=$db->query('SELECT region_key,label,updated_at,last_used_at,permanent FROM or_regions ORDER BY permanent DESC,region_key');
    if($q)while($r=$q->fetch())$out[]=$r;return $out;
}
function openroad_enqueue_region(PDO $db,string $region,string $reason='destination'): array {
    if($region==='london')return ['region'=>'london','state'=>'direct','label'=>'London · TfL direct'];
    $cfg=openroad_region_config($region);if(!$cfg)return ['region'=>$region,'state'=>'unsupported','label'=>'Unsupported area'];
    $ds=openroad_region_dataset($db,$region);
    if($ds>0){openroad_region_touch($db,$region);return ['region'=>$region,'state'=>'ready','label'=>$cfg['label']??$region];}
    $q=$db->prepare('INSERT INTO or_prepare_queue(region_key,reason,requested_at,last_requested_at,attempts,last_error) VALUES(?,?,NOW(),NOW(),0,NULL) ON DUPLICATE KEY UPDATE reason=VALUES(reason),last_requested_at=NOW()');$q->execute([$region,$reason]);
    return ['region'=>$region,'state'=>'queued','label'=>$cfg['label']??$region];
}
