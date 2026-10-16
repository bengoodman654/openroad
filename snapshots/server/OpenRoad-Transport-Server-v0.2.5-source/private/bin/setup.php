<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/auth.php';
try{
  $db=openroad_db();openroad_schema($db);openroad_server_secret();$code=openroad_issue_pairing_code($db);
  echo "OpenRoad Transport Server v0.2.3 is initialised.\n";
  echo "One-time pairing code (expires in ".(int)(openroad_config()['pairing_minutes']??30)." minutes):\n\n  $code\n\n";
  echo "Enter this code in OpenRoad > Settings > OpenRoad private transport server.\n";
  echo "Do not upload or publish the code. It becomes invalid after the first successful pairing.\n";
}catch(Throwable $e){fwrite(STDERR,'Setup failed: '.$e->getMessage().PHP_EOL);exit(1);}
