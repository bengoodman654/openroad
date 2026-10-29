<?php
require_once __DIR__.'/retire_legacy_gtfs_cron.php';
function chk(bool $yes,string $name):void{
    if(!$yes)throw new RuntimeException('FAIL '.$name);
    echo "PASS ".$name."\n";
}
function rejected(string $value,string $name):void {
    try {or_retire_legacy_full_gtfs_cron($value);}
    catch(RuntimeException $e){chk(true,$name);return;}
    throw new RuntimeException('FAIL '.$name);
}
$other="0 * * * * /usr/bin/php /home/user/mail-maintenance.php\n";
$job="17 3 * * * /opt/alt/php82/usr/bin/php /home/user/openroad-private/bin/update_gtfs.php south_west >> /home/user/gtfs.log 2>&1\n";
$a=or_retire_legacy_full_gtfs_cron($other.$job);
chk($a['newCrontab']===$other,'unrelated email cron preserved byte-for-byte');
chk($a['retiredEntries']===1,'one nightly full import retired');
$multi=$job.$job.$other;
rejected($multi,'two full import jobs refused');
rejected("18 3 * * * /usr/bin/php /private/bin/update_gtfs.php\n".$other,
         'unrecognised cron schedule refused');
rejected($other,'missing target refused');
rejected("# ".$job.$other,'commented job never modified');
rejected("17 3 * * * /usr/bin/php /private/bin/other.php\n",
         'unrelated cron untouched');
$masked="0 0 * * * /usr/bin/php /home/user/mail-token-A_SECRET.php\n";
$b=or_retire_legacy_full_gtfs_cron($masked.$job);
chk($b['newCrontab']===$masked,'other service secrets untouched and not printed');
echo "Exact legacy cron retirement safeguards: ALL CHECKS PASSED\n";
