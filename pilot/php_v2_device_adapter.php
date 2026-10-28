<?php
declare(strict_types=1);

/**
 * Private research adapter for OpenRoad's EXISTING verified device identity.
 * This is a library, not a public route. No PHP-FPM workers are killed here.
 */
require_once __DIR__ . '/php_v2_cancellation.php';

function ptv2_authenticated_device(array $auth): string {
    // Only pass the return value of openroad_require_signed(), NEVER JSON
    // supplied by the client, into this helper.
    $device = $auth['deviceId'] ?? null;
    if (!is_string($device) ||
        !preg_match('/^[0-9a-fA-F-]{36}$/D', $device)) {
        throw new RuntimeException('No authenticated paired device');
    }
    return $device;
}

/** $snapshot MUST be selected by the server capability manifest. */
function ptv2_issue_for_device(
    OpenRoadV2ResearchCancellation $registry, array $auth,
    array $request, string $serverPinnedSnapshot, int $now,
    ?string $requestHash = null
): array {
    $principal = ptv2_authenticated_device($auth);
    $session = $request['sessionId'] ?? null;
    $generation = $request['generation'] ?? null;
    if (!is_string($session) || !is_int($generation) ||
        !preg_match('/^[A-Za-z0-9_-]{1,128}$/D', $session) ||
        $serverPinnedSnapshot === '') {
        throw new InvalidArgumentException('Invalid request lifecycle input');
    }
    $token = $registry->issue(
        $principal, $session, $generation, $serverPinnedSnapshot, $now,
        60, null, $requestHash);
    // No route is admitted by simply issuing a ticket.
    return ['taskTicket' => $token, 'status' => 'ISSUED_ONLY',
            'researchOnly' => true];
}

function ptv2_cancel_for_device(
    OpenRoadV2ResearchCancellation $registry, array $auth,
    array $request, int $now
): array {
    $principal = ptv2_authenticated_device($auth);
    $token = $request['taskTicket'] ?? null;
    if (!is_string($token) || strlen($token) > 1024 || $token === '') {
        throw new InvalidArgumentException('Missing bounded cancellation ticket');
    }
    $state = $registry->cancel($token, $principal, $now);
    return [
        'outcome' => in_array($state, ['STOPPING','STOPPED','COMPLETED'], true)
                     ? 'OK' : 'RATE_LIMITED',
        'remoteJobStatus' => $state,
        'researchOnly' => true,
    ];
}
