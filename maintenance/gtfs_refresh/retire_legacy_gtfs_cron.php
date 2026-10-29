<?php
declare(strict_types=1);
/**
 * Narrow transformation of one cPanel cron job.
 * No shell execution, no file reads of /etc, never prints old cron lines.
 * The invoking workflow controls installation and backs up the crontab.
 */
function or_retire_legacy_full_gtfs_cron(string $source): array {
    $hasFinalNewline = str_ends_with($source, "\n");
    $lines = explode("\n", str_replace("\r\n", "\n", $source));
    if ($hasFinalNewline) array_pop($lines);
    $matched = [];
    $unrecognised = [];
    foreach ($lines as $i => $line) {
        $trimmed = ltrim($line);
        if ($trimmed === '' || $trimmed[0] === '#') continue;
        if (!preg_match('/(?:^|[^a-zA-Z0-9_])update_gtfs\.php(?:\s|$|["\x27])/', $line)) continue;
        // Exact existing 03:17 daily scheduled full GTFS import only.
        if (!preg_match('/^\s*17\s+3\s+\*\s+\*\s+\*\s+/', $line)) {
            $unrecognised[] = $i;
            continue;
        }
        // Only regular cron commands, not shell fragments or malformed data.
        if (str_contains($line, "\0") || strlen($line) > 4096) {
            $unrecognised[] = $i;
            continue;
        }
        $matched[] = $i;
    }
    if (count($matched) !== 1 || $unrecognised) {
        throw new RuntimeException('Ambiguous or absent retired GTFS daily cron target');
    }
    unset($lines[$matched[0]]);
    $out = implode("\n", array_values($lines));
    if ($hasFinalNewline && $out !== '') $out .= "\n";
    if ($out === $source) throw new RuntimeException('Crontab transformation did not change source');
    return [
        'newCrontab'=>$out,
        'retiredEntries'=>1,
        'remainingLines'=>count($lines)-1,
    ];
}
if (PHP_SAPI==='cli' && realpath($argv[0]??'')===__FILE__) {
    if (count($argv)!==3) {fwrite(STDERR,"Usage: retire.php in out\n");exit(2);}
    $in=file_get_contents($argv[1]);
    if ($in===false) {fwrite(STDERR,"Cannot read crontab input\n");exit(2);}
    try {
        $res=or_retire_legacy_full_gtfs_cron($in);
        if (file_put_contents($argv[2], $res['newCrontab'])===false)
            throw new RuntimeException('Unable to write cron output');
        echo "CRON_RETIRE_PLAN exact_daily_gtfs_jobs=1 unrelated_entries_preserved=yes\n";
    } catch(Throwable $e) {
        fwrite(STDERR,"CRON_RETIRE_REFUSED ambiguous_original_entry\n");exit(3);
    }
}
