# OpenRoad public transport v2 — off-host integration handover
**Date:** 28 October 2026
**Branch:** pt-v2-planner-hardening
**State:** SOURCE-STAGED, TESTED OFF-HOST, NOT DEPLOYED, NOT FIELD-READY

## What now actually exists

### PHP staged server from v0.2.5
- A dedicated **research-only** \`/api/v2/task.php\` endpoint in a
  separately built source ZIP, NOT under production hosting. Four
  authenticated actions: issue, route, cancel, status.
- Uses existing paired-device ECDSA signature verification
  (openroad_require_signed) to establish the caller identity.
  A separate short-lived HMAC ticket binds the requesting device,
  task/session/generation, exact canonical origin/destination/preferences,
  and a server-selected pinned dataset/region identifier.
- Route changes are strictly isolated from existing v1 endpoints.
  The staged PHP router has an optional cancellation callback inserted
  at the existing routing budget checkpoints. The production router is
  unchanged; original callers remain valid without supplying a callback.
- A private locked state-file registry (maximum two active workers, 128
  records) supports atomic cancel-before-start, cooperative cancellation,
  status acknowledgment and cleanup of abandoned STOPPING leases. Shared
  or unrelated jobs are not cancelled.
- All research output is explicitly **nonselectable**, with no navigation
  legs exposed; exact stop-side pedestrian access is not verified.
- Endpoint refuses service unless a separate, private
  \`pt_v2_hmac_secret\` is configured in the server's existing secret store.
  Do NOT paste keys into chat or commit them to GitHub.
- The new versioned endpoint is not deployed or wired to any live PHP-FPM
  process. Actual MySQL/MariaDB and shared-host pressure remain untested.

### Android staged source from v0.6.31
- Source-based update to app.js and index.html inserts the left Back arrow
  and makes the Where to? X cancel a foreground PT search without clearing
  current guidance. X requires confirmation to stop active guidance.
- OpenRoadServerClient.java adds signed issue/route/cancel/status v2 methods
  using the app's existing paired-device signature and server URL.
- TransitClient.java has a **BuildConfig.DEBUG-gated** research transport
  path, disabled by default, with an active-ticket lifecycle and a bounded
  separate cancellation executor. A ticket arriving after local cancel is
  also cancelled. No v2 result is sent to the legacy route-success path.
- Research mode explicitly rejects added intermediate stops rather than
  silently omitting them. Normal v1 routes remain unchanged.
- This is a staged DEBUG compilation, not an installable production release;
  no APK was published through the updater and no app was pushed to a phone.

## Evidence — all independently successful

- Android staging, exact UI-handler tests, source validation and Gradle
  debug build:
  https://github.com/bengoodman654/openroad/actions/runs/40706004620
- PHP full staged server, endpoint tests, original v0.2.5 server unit
  regressions, independent-process cancellation, crash lease recovery,
  and PHP syntax validation:
  https://github.com/bengoodman654/openroad/actions/runs/40706736109
- Python pilot regression: 147 discovered, 146 passed, 1 optional skip,
  zero failures:
  https://github.com/bengoodman654/openroad/actions/runs/40706602006
- Previously independent Bristol/Coventry GTFS↔OSM exact stop-code audit:
  pilot/real-stop-crosswalk-evidence-2026-10-27.json

None of these is a 105-case physical/production acceptance pass.

## Release blockers — require live or human input

1. Permission to create an isolated, rate-limited **test-only** v2 endpoint
   on JustHostMe. Test endpoint must use distinct secret/cache paths,
   strong device access, rollback and must not replace the v1 public API
   or impact hosted websites/email. Obtain an actual live CPU/IO baseline
   read-only before allowing heavy requests.
2. Explicit permission and participation to install a test-only Android
   APK on the user's Fairphone, validate X/Back, and report real
   Bristol/Coventry journey results and cancellation states.
3. Server-side creation of the new signing secret using a secure generator.
   Never request its value in chat. Confirm which API credentials and rail
   source entitlements actually exist; do not assume UK-wide routing.
4. Real paired-device HTTPS/HTTP cancellation handshake under network
   errors, multiple PHP-FPM workers, server restarts, snapshot replacement
   and website/email load — none verified against live infrastructure.
5. Independent safe, legal and accessible pedestrian stop-side connectors
   and actual full route geometry in Bristol/Coventry. Existing stop
   *identity* observations are not walking or boarding/accessibility proof.
6. Complete acceptance coverage (105 cases), reproducible measured
   <20-second first *complete* result when a feasible service exists, and
   actual debugging of Coventry no-route conditions on the phone.
7. A production rollback plan, installation/signature compatibility and
   the user's separate authorisation before any deployment or release.

## Minimal safe next action after user approval

- Start with read-only JustHostMe resource/version checks (not imports,
  cron or heavy server jobs).
- Establish an isolated restricted research endpoint with independently
  generated private secret and bounded request quotas, without touching v1.
- Perform signed-device handshake and cancellation with ONE synthetic
  cheap route and verify immediate zero-result suppression on cancelled
  requests, concurrent tasks, and remote STOPPING/STOPPED/UNKNOWN states.
- Provide a separate test APK, not a production auto-update; the user
  chooses when to install and may roll back.
- Only after successful manual trials, continue real-data and accessibility
  gates. Do not merge or deploy any release prematurely.

No direct production deployment or Android updater action is authorised
by the existence of this report.
