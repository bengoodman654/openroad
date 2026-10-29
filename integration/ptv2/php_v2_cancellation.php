<?php
declare(strict_types=1);

/**
 * Off-host PT v2 PHP cancellation reference, NOT a production endpoint.
 * No network calls, cron, credentials, global process kills or host deployment.
 * The caller MUST obtain $authenticatedPrincipal from genuine server auth,
 * never trust a user-supplied principal or a public session ID.
 */
final class OpenRoadV2ResearchCancellation {
    private string $directory;
    private string $secret;
    private int $maxActive;
    private int $maxRecords;

    public function __construct(string $directory, string $secret,
                                int $maxActive = 2, int $maxRecords = 128) {
        if (!is_dir($directory) || is_link($directory) ||
            (fileperms($directory) & 0077) !== 0 ||
            strlen($secret) < 32 || $maxActive < 1 ||
            $maxRecords < $maxActive || $maxRecords > 2048) {
            throw new InvalidArgumentException('Unsafe private registry config');
        }
        $this->directory = (string)realpath($directory);
        $this->secret = $secret;
        $this->maxActive = $maxActive;
        $this->maxRecords = $maxRecords;
    }

    private static function b64(string $value): string {
        return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
    }

    public function issue(string $principal, string $sessionId,
                          int $generation, string $snapshotId, int $now,
                          int $ttlSeconds = 60, ?string $taskId = null,
                          ?string $requestHash = null): string {
        if (!preg_match('/^[A-Za-z0-9_-]{1,128}$/D', $principal) ||
            !preg_match('/^[A-Za-z0-9_-]{1,128}$/D', $sessionId) ||
            !preg_match('/^[A-Za-z0-9_:.-]{1,128}$/D', $snapshotId) ||
            ($taskId !== null &&
             !preg_match('/^[A-Za-z0-9_-]{1,128}$/D', $taskId)) ||
            ($requestHash !== null &&
             !preg_match('/^[a-f0-9]{64}$/D', $requestHash)) ||
            $generation < 0 || $generation > 2147483647 ||
            $ttlSeconds < 1 || $ttlSeconds > 180) {
            throw new InvalidArgumentException('Invalid ticket properties');
        }
        $fields = [
            'principal' => $principal, 'session' => $sessionId,
            'task' => $taskId ?? bin2hex(random_bytes(16)),
            'generation' => $generation, 'snapshot' => $snapshotId,
            'iat' => $now, 'exp' => $now + $ttlSeconds,
            'queryHash' => $requestHash,
        ];
        $body = self::b64(json_encode($fields, JSON_THROW_ON_ERROR));
        return $body . '.' . self::b64(
            hash_hmac('sha256', $body, $this->secret, true));
    }

    private function inspect(string $token, string $principal): array {
        if (strlen($token) > 1024 || substr_count($token, '.') !== 1) {
            throw new RuntimeException('Invalid task token');
        }
        [$body, $signature] = explode('.', $token);
        $expected = self::b64(hash_hmac('sha256', $body, $this->secret, true));
        if (!hash_equals($expected, $signature)) {
            throw new RuntimeException('Task signature mismatch');
        }
        $raw = base64_decode(strtr($body, '-_', '+/'), true);
        if (!is_string($raw) || strlen($raw) > 1024) {
            throw new RuntimeException('Invalid task payload');
        }
        $value = json_decode($raw, true, 10, JSON_THROW_ON_ERROR);
        if (!is_array($value) || ($value['principal'] ?? null) !== $principal ||
            !isset($value['session'], $value['task'], $value['generation'],
                   $value['snapshot'], $value['iat'], $value['exp']) ||
            !is_string($value['session']) || !is_string($value['task']) ||
            !is_string($value['snapshot']) ||
            !is_int($value['generation']) || !is_int($value['iat']) ||
            !is_int($value['exp']) || $value['generation'] < 0 ||
            (array_key_exists('queryHash',$value) &&
              $value['queryHash'] !== null &&
              (!is_string($value['queryHash']) ||
               !preg_match('/^[a-f0-9]{64}$/D',$value['queryHash']))) ||
            $value['exp'] <= $value['iat'] ||
            $value['exp'] - $value['iat'] > 180) {
            throw new RuntimeException('Task ownership or lease invalid');
        }
        $value['_key'] = hash('sha256', $principal . "\x00" .
            $value['session'] . "\x00" . $value['task'] . "\x00" .
            (string)$value['generation']);
        $value['_fingerprint'] = hash('sha256', $token);
        return $value;
    }

    /** Lock/write shared file, no unsafe per-worker globals or background jobs. */
    private function transaction(int $now, callable $action, bool $write = true) {
        $lockFile = $this->directory . '/ptv2.lock';
        $stateFile = $this->directory . '/ptv2.json';
        if (is_link($lockFile) || is_link($stateFile)) {
            throw new RuntimeException('Unsafe registry symlink');
        }
        $lock = @fopen($lockFile, 'c');
        if ($lock === false || !flock($lock, LOCK_EX)) {
            throw new RuntimeException('Registry lock unavailable; deny work');
        }
        try {
            @chmod($lockFile, 0600);
            $state = ['records' => [], 'denyUntil' => 0];
            if (is_file($stateFile)) {
                if (filesize($stateFile) > 100000) {
                    throw new RuntimeException('Registry oversized; deny work');
                }
                $raw = @file_get_contents($stateFile);
                $parsed = is_string($raw) ? json_decode($raw, true) : null;
                if (!is_array($parsed) ||
                    !is_array($parsed['records'] ?? null) ||
                    !is_int($parsed['denyUntil'] ?? null)) {
                    throw new RuntimeException('Registry corrupt; deny work');
                }
                $state = $parsed;
            }
            foreach ($state['records'] as $key => &$record) {
                if (!isset($record['exp'], $record['status']) ||
                    !is_int($record['exp'])) {
                    throw new RuntimeException('Registry record corrupt');
                }
                if ($now >= $record['exp'] && $record['status'] === 'RUNNING') {
                    $record['status'] = 'STOPPING';
                }
                // Abandoned STOPPING workers must not exhaust capacity forever.
                // Removal is UNKNOWN, never a fabricated STOPPED acknowledgement.
                if (in_array($record['status'], ['STOPPED','COMPLETED','STOPPING'], true) &&
                    $now >= $record['exp'] + 15) {
                    unset($state['records'][$key]);
                }
            }
            unset($record);
            $response = $action($state);
            if ($write) {
                $json = json_encode($state, JSON_THROW_ON_ERROR);
                if (strlen($json) > 100000) {
                    throw new RuntimeException('Registry limit; deny work');
                }
                $tmp = tempnam($this->directory, 'ptv2_');
                if ($tmp === false) {
                    throw new RuntimeException('Registry write unavailable');
                }
                try {
                    chmod($tmp, 0600);
                    if (file_put_contents($tmp, $json) !== strlen($json) ||
                        !rename($tmp, $stateFile)) {
                        throw new RuntimeException('Registry atomic write failed');
                    }
                } finally {
                    if (is_file($tmp)) unlink($tmp);
                }
            }
            return $response;
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    private static function currentRecord(array &$state, array $ticket): ?array {
        $record = $state['records'][$ticket['_key']] ?? null;
        if ($record !== null &&
            ($record['fingerprint'] ?? null) !== $ticket['_fingerprint']) {
            throw new RuntimeException('Immutable task identity reused');
        }
        return $record;
    }

    public function register(string $token, string $principal, int $now): string {
        $t = $this->inspect($token, $principal);
        return $this->transaction($now, function (&$state) use ($t, $now) {
            if ($now < $t['iat'] || $now >= $t['exp']) return 'REJECTED_EXPIRED';
            $record = self::currentRecord($state, $t);
            if ($record !== null) {
                return $record['status'] === 'RUNNING' ?
                    'DUPLICATE_RUNNING' : 'REJECTED_CANCELLED';
            }
            if ($now < $state['denyUntil']) return 'RATE_LIMITED';
            $active = 0;
            foreach ($state['records'] as $record) {
                if (in_array($record['status'],
                             ['RUNNING', 'STOPPING'], true)) $active++;
            }
            if ($active >= $this->maxActive ||
                count($state['records']) >= $this->maxRecords) {
                return 'RATE_LIMITED';
            }
            $state['records'][$t['_key']] = [
                'fingerprint' => $t['_fingerprint'],
                'exp' => $t['exp'], 'status' => 'RUNNING',
            ];
            return 'RUNNING';
        });
    }

    public function cancel(string $token, string $principal, int $now): string {
        $t = $this->inspect($token, $principal);
        return $this->transaction($now, function (&$state) use ($t, $now) {
            $record = self::currentRecord($state, $t);
            if ($record !== null) {
                if ($record['status'] === 'RUNNING') {
                    $state['records'][$t['_key']]['status'] = 'STOPPING';
                    return 'STOPPING';
                }
                return $record['status'];
            }
            if ($now >= $t['exp']) return 'REJECTED_EXPIRED';
            if (count($state['records']) >= $this->maxRecords) {
                $state['denyUntil'] = max($state['denyUntil'], $t['exp']);
                return 'STOPPING_CAPACITY_BLOCK';
            }
            $state['records'][$t['_key']] = [
                'fingerprint' => $t['_fingerprint'],
                'exp' => $t['exp'], 'status' => 'STOPPED',
            ];
            return 'STOPPED';
        });
    }

    public function shouldStop(string $token, string $principal,
                               int $now): bool {
        $t = $this->inspect($token, $principal);
        return $this->transaction($now, function (&$state) use ($t, $now) {
            $r = self::currentRecord($state, $t);
            return $now >= $t['exp'] || $r === null ||
                   $r['status'] !== 'RUNNING';
        }, false);
    }

    /** Signed ticket claims, never accepted from the request body directly. */
    public function verifiedClaims(string $token, string $principal): array {
        $t = $this->inspect($token, $principal);
        return [
            'deviceId' => $t['principal'],
            'sessionId' => $t['session'],
            'taskId' => $t['task'],
            'generation' => $t['generation'],
            'snapshotId' => $t['snapshot'],
            'queryHash' => $t['queryHash'] ?? null,
            'expiresAt' => $t['exp'],
        ];
    }

    public function status(string $token, string $principal, int $now): string {
        $t = $this->inspect($token, $principal);
        return $this->transaction($now, static function(&$state) use($t) {
            $r = self::currentRecord($state,$t);
            return $r===null ? 'UNKNOWN' : $r['status'];
        }, false);
    }

    public function finish(string $token, string $principal, int $now): string {
        $t = $this->inspect($token, $principal);
        return $this->transaction($now, function (&$state) use ($t) {
            $r = self::currentRecord($state, $t);
            if ($r === null) return 'UNKNOWN';
            $status = $r['status'] === 'RUNNING' ? 'COMPLETED' :
                      ($r['status'] === 'STOPPING' ? 'STOPPED' : $r['status']);
            $state['records'][$t['_key']]['status'] = $status;
            return $status;
        });
    }
}
