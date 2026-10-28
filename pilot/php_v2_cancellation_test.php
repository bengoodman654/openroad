<?php
declare(strict_types=1);
require_once __DIR__ . '/php_v2_cancellation.php';

function check(bool $pass, string $name): void {
    if (!$pass) throw new RuntimeException('FAILED: ' . $name);
    echo "PASS: " . $name . "\n";
}
function raises(callable $fn, string $name): void {
    try { $fn(); } catch (Throwable $e) {
        check(true, $name);
        return;
    }
    throw new RuntimeException('FAILED: ' . $name);
}
$dir = sys_get_temp_dir() . '/or-ptv2-' . bin2hex(random_bytes(8));
mkdir($dir, 0700);
try {
    $secret = str_repeat('S', 32);
    $r = new OpenRoadV2ResearchCancellation($dir, $secret, 2, 3);
    $a = $r->issue('A', 'sessionA', 1, 'feed', 100, 40, 'task-a');
    $b = $r->issue('B', 'sessionB', 1, 'feed', 100, 40, 'task-b');
    $c = $r->issue('A', 'sessionA', 2, 'feed', 100, 40, 'task-c');
    $d = $r->issue('A', 'sessionA', 3, 'feed', 100, 40, 'task-d');

    check($r->cancel($a, 'A', 100) === 'STOPPED', 'cancel before job registration');
    check($r->register($a, 'A', 101) === 'REJECTED_CANCELLED',
          'late job cannot revive tombstone');
    check($r->cancel($a, 'A', 101) === 'STOPPED', 'idempotent cancellation');

    check($r->register($b, 'B', 101) === 'RUNNING', 'second owner register');
    check(!$r->shouldStop($b, 'B', 101), 'running work not spuriously cancelled');
    check($r->cancel($b, 'B', 102) === 'STOPPING',
          'running cancellation is STOPPING, not falsely STOPPED');
    check($r->shouldStop($b, 'B', 102), 'worker detects cancellation');
    check($r->finish($b, 'B', 102) === 'STOPPED', 'worker acknowledges stop');

    raises(fn() => $r->cancel($b, 'A', 102),
           'different authenticated principal cannot cancel job');
    $tampered = substr_replace($b, 'Z', 8, 1);
    raises(fn() => $r->register($tampered, 'B', 102),
           'tampered HMAC ticket rejected');
    check($r->register($c, 'A', 103) === 'RUNNING', 'new task admitted');
    check($r->register($c, 'A', 103) === 'DUPLICATE_RUNNING',
          'duplicate job cannot start twice');
    check($r->finish($c, 'A', 104) === 'COMPLETED', 'completion acknowledged');
    check($r->cancel($c, 'A', 104) === 'COMPLETED',
          'completed job never falsely claims it was killed');

    check($r->cancel($d, 'A', 105) === 'STOPPING_CAPACITY_BLOCK',
          'saturated tombstone storage fails closed');
    check($r->register($d, 'A', 105) === 'RATE_LIMITED',
          'saturation does not run the late task');

    check($r->register($d, 'A', 141) === 'REJECTED_EXPIRED',
          'expired ticket cannot be revived after store expiry');
    $e = $r->issue('A', 'sessionA', 4, 'feed', 142, 10, 'task-e');
    check($r->register($e, 'A', 142) === 'RUNNING',
          'cleaned expired records admit fresh work');
    check($r->shouldStop($e, 'A', 153),
          'expired running lease is cooperatively cancelled');
    check($r->finish($e, 'A', 153) === 'STOPPED',
          'lease cancellation does not falsely claim early stop');

    raises(fn() => new OpenRoadV2ResearchCancellation($dir, 'weak'),
           'weak signing secret is rejected');

    echo "PHP cancellation reference: ALL TESTS PASSED\n";
} finally {
    foreach (glob($dir . '/*') ?: [] as $file) unlink($file);
    rmdir($dir);
}
