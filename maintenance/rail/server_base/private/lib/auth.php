<?php
require_once __DIR__ . '/bootstrap.php';

function openroad_headers_lower(): array {
    $out=[];
    if(function_exists('getallheaders')) foreach((array)getallheaders() as $k=>$v) $out[strtolower((string)$k)]=(string)$v;
    foreach($_SERVER as $k=>$v) if(str_starts_with($k,'HTTP_')) $out[strtolower(str_replace('_','-',substr($k,5)))]=(string)$v;
    return $out;
}
function openroad_client_ip_hash(): string {
    $ip=(string)($_SERVER['REMOTE_ADDR']??'unknown');
    return hash_hmac('sha256',$ip,openroad_server_secret());
}
function openroad_rate_limit(PDO $db,string $bucket,int $limit,int $windowSeconds): void {
    $hash=hash_hmac('sha256',$bucket,openroad_server_secret());
    $cutoff=date('Y-m-d H:i:s',time()-$windowSeconds);
    $q=$db->prepare('SELECT COUNT(*) FROM or_rate_events WHERE bucket_hash=? AND event_at>=?');
    $q->execute([$hash,$cutoff]);
    if((int)$q->fetchColumn()>=$limit) openroad_json(['ok'=>false,'error'=>'Too many requests'],429);
    $q=$db->prepare('INSERT INTO or_rate_events(bucket_hash,event_at) VALUES(?,NOW())');$q->execute([$hash]);
    if(random_int(1,40)===1) $db->exec("DELETE FROM or_rate_events WHERE event_at < (NOW() - INTERVAL 1 DAY)");
}
function openroad_base64url_decode(string $s): string|false {
    if(!preg_match('/^[A-Za-z0-9_-]+$/',$s)) return false;
    $pad=(4-(strlen($s)%4))%4;
    return base64_decode(strtr($s,'-_','+/').str_repeat('=',$pad),true);
}
function openroad_request_path(): string {
    $p=parse_url((string)($_SERVER['REQUEST_URI']??''),PHP_URL_PATH);
    return is_string($p)&&$p!==''?$p:'/';
}
function openroad_is_https(): bool {
    $https=strtolower((string)($_SERVER['HTTPS']??''));
    return $https==='on'||$https==='1'||(string)($_SERVER['SERVER_PORT']??'')==='443';
}
function openroad_validate_public_key(string $pem): bool {
    if(strlen($pem)<120||strlen($pem)>2000) return false;
    $key=@openssl_pkey_get_public($pem); if($key===false)return false;
    $d=openssl_pkey_get_details($key); if(!is_array($d)||($d['type']??null)!==OPENSSL_KEYTYPE_EC)return false;
    $curve=(string)($d['ec']['curve_name']??'');
    return in_array($curve,['prime256v1','secp256r1'],true) && (int)($d['bits']??0)>=256;
}
function openroad_generate_pairing_code(): string {
    $alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';$raw='';
    for($i=0;$i<16;$i++)$raw.=$alphabet[random_int(0,strlen($alphabet)-1)];
    return implode('-',str_split($raw,4));
}
function openroad_issue_pairing_code(PDO $db,?int $minutes=null): string {
    $cfg=openroad_config();$mins=$minutes??(int)($cfg['pairing_minutes']??30);$code=openroad_generate_pairing_code();
    openroad_set_setting($db,'pairing_hash',password_hash($code,PASSWORD_DEFAULT));
    openroad_set_setting($db,'pairing_expires',(string)(time()+max(5,$mins)*60));
    return $code;
}
function openroad_pair_device(PDO $db,array $data): array {
    $cfg=openroad_config();openroad_rate_limit($db,'pair-ip:'.openroad_client_ip_hash(),(int)($cfg['pair_attempts_per_minute']??8),60);
    $code=strtoupper(trim((string)($data['pairingCode']??'')));
    $deviceId=trim((string)($data['deviceId']??''));$pem=(string)($data['publicKeyPem']??'');$label=trim((string)($data['deviceLabel']??'OpenRoad Android'));
    if(!preg_match('/^[0-9a-fA-F-]{36}$/',$deviceId)||!openroad_validate_public_key($pem)) openroad_json(['ok'=>false,'error'=>'Pairing failed'],401);
    $hash=(string)(openroad_setting($db,'pairing_hash','')??'');$exp=(int)(openroad_setting($db,'pairing_expires','0')??0);
    if($hash===''||$exp<time()||$code===''||!password_verify($code,$hash)) openroad_json(['ok'=>false,'error'=>'Pairing failed'],401);
    $label=preg_replace('/[^\pL\pN ._\-]/u','',$label)?:'OpenRoad Android';$label=mb_substr($label,0,120);
    $q=$db->prepare('INSERT INTO or_devices(device_id,public_key_pem,device_label,created_at,last_seen_at,revoked_at) VALUES(?,?,?,NOW(),NOW(),NULL) ON DUPLICATE KEY UPDATE public_key_pem=VALUES(public_key_pem),device_label=VALUES(device_label),last_seen_at=NOW(),revoked_at=NULL');
    $q->execute([$deviceId,$pem,$label]);
    openroad_set_setting($db,'pairing_hash','');openroad_set_setting($db,'pairing_expires','0');
    return ['deviceId'=>$deviceId,'deviceLabel'=>$label];
}
function openroad_require_signed(PDO $db,string $body): array {
    if(!openroad_is_https()) openroad_json(['ok'=>false,'error'=>'HTTPS required'],400);
    $cfg=openroad_config();openroad_rate_limit($db,'unsigned-ip:'.openroad_client_ip_hash(),(int)($cfg['unsigned_attempts_per_minute']??30),60);
    $h=openroad_headers_lower();$device=trim($h['x-openroad-device']??'');$ts=(int)($h['x-openroad-timestamp']??0);$nonce=trim($h['x-openroad-nonce']??'');$sig=trim($h['x-openroad-signature']??'');
    if(!preg_match('/^[0-9a-fA-F-]{36}$/',$device)||$ts<=0||strlen($nonce)<16||strlen($nonce)>80||strlen($sig)<40) openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);
    if(abs(time()-$ts)>(int)($cfg['signed_clock_skew_seconds']??180)) openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);
    $q=$db->prepare('SELECT public_key_pem,device_label FROM or_devices WHERE device_id=? AND revoked_at IS NULL LIMIT 1');$q->execute([$device]);$row=$q->fetch();if(!$row)openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);
    $sigBytes=openroad_base64url_decode($sig);if($sigBytes===false)openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);
    $canonical="OPENROAD1\nPOST\n".openroad_request_path()."\n".$ts."\n".$nonce."\n".$device."\n".hash('sha256',$body);
    $ok=openssl_verify($canonical,$sigBytes,$row['public_key_pem'],OPENSSL_ALGO_SHA256);
    if($ok!==1)openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);
    $nonceHash=hash('sha256',$nonce);$prune=(int)($cfg['nonce_retention_seconds']??900);
    $db->exec('DELETE FROM or_nonces WHERE created_at < (NOW() - INTERVAL '.max(300,$prune).' SECOND)');
    try{$q=$db->prepare('INSERT INTO or_nonces(device_id,nonce_hash,created_at) VALUES(?,?,NOW())');$q->execute([$device,$nonceHash]);}
    catch(PDOException $e){if((string)$e->getCode()==='23000')openroad_json(['ok'=>false,'error'=>'Unauthorised'],401);throw $e;}
    openroad_rate_limit($db,'device:'.$device,(int)($cfg['device_requests_per_minute']??120),60);
    $q=$db->prepare('UPDATE or_devices SET last_seen_at=NOW() WHERE device_id=?');$q->execute([$device]);
    return ['deviceId'=>$device,'deviceLabel'=>$row['device_label']];
}
