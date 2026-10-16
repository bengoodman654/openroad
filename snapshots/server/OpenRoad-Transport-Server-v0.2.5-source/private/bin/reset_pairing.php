<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/auth.php';
try{$db=openroad_db();openroad_schema($db);$code=openroad_issue_pairing_code($db);echo "New one-time OpenRoad pairing code:\n\n  $code\n\nExpires in ".(int)(openroad_config()['pairing_minutes']??30)." minutes and becomes invalid after one successful pairing.\n";}
catch(Throwable $e){fwrite(STDERR,'Could not create pairing code: '.$e->getMessage().PHP_EOL);exit(1);}
