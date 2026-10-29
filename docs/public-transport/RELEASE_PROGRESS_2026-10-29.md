# OpenRoad completion: timetable and walking-connection integration checkpoint
Date: 29 October 2026. This note supersedes older provisional statements about a broken 03:17 GTFS cron being present.

## Working production is unchanged
The user has confirmed Android 0.6.32 public transport works through proxied Cloudflare. The live PHP v0.2.9 route planner was not replaced and still uses the existing MariaDB timetable. The South West service-date calendar is maintained through 13 December 2026 using the installed private calendar-only script.

## Default-branch maintenance now configured
- GitHub main: .github/workflows/openroad-calendar-main.yml. Source/syntax check passed (run 40865492662). Scheduled Monday 04:19 UTC or manual-dispatch work checks SHA-256 of existing private PHP files and runs only the bounded service-calendar extension. IMPORTANT: the first scheduled execution has not yet occurred; a successful source-check job is not a successful calendar extension.
- GitHub main: .github/workflows/openroad-feed-main.yml. Source/unit checks passed (run 40865740941). Weekly official South West/West Midlands feed validation runs on GitHub runners only; it does NOT import the database or deploy SQLite indexes.
- Read-only crontab audit (run 40866472144) found NO update_gtfs.php cron entry. Two other cron entries were classified and left completely unchanged. The old 03:17 job should NOT be retired again. The audit safely reports already_absent=yes.

## Server+Android source integration unchanged
PHP v2 signed/cancellable source against exact v0.2.9: run 40862736632 passed.
Android v2 signed adapter compiled on actual v0.6.32 source: run 40862736509 passed.
Research endpoint and adapter remain disabled for selectable live navigation.

## Fresh-feed research — confirmed coverage gap
The new research SQLite sources were built and compacted off-host from official BODS for both regions. West Midlands returned 3 nonselectable research journeys; the South West indexed source initially returned NO_JOURNEY for representative South Bristol-to-Clifton points.

Code improvements on this branch:
- maintenance/gtfs_refresh/query_sqlite.py: cooperative SQLite progress handler can interrupt SQL during cancellation or a computation deadline (not only between queries).
- The old sorted-first-600 first-leg-transfer sampling was removed and replaced with bounded destination-driven matching of active drop-off trips to earlier boardings at the exact SAME stop ID; dense-service regression tests pass.
- A hard 20-stop cap was replaced by a bounded radius-dependent 24-to-48-stop selection; no hidden widening of the user's walking preference.
- Research results now include independently labelled great-circle lower bounds on first/final walking distances, explicitly NOT navigable geometry.

Evidence:
- Full indexed build and updated backend tests: 40866081561 and 40866044894.
- Existing compact index, no rebuild: 40866793270 and 40867103145.
- More detailed coverage and transfer audit against same index: 40867386515.

A representative query on 29 October at both 09:00 and 17:45 found:
- 900m and 1200m stop-search radii: NO_JOURNEY.
- 1600m and 1800m radii: three *research-only, nonselectable* schedules, ~90–180ms SQL search time.
- The first result at 1600m required approx 234m great-circle access walk plus 1316m (09:00) or 1344m (17:45) great-circle egress walk. Actual route would be longer; this does NOT satisfy a 10-minute walking limit.
- Destination service coverage is NOT missing: at 900m radius there were 646 indexed destination arrivals in the audit window, 886 scheduled origin boardings, and 189 active service IDs for 2026-10-29. There was no matched same-stop itinerary under the requested smaller radius. The next planner task is genuine between-stop pedestrian transfer connectivity, not inventing longer access walks or altering the user's preference.

## Outstanding release blockers
- Find and verify directional stop-side pedestrian access and legal crossings (OSM network plus official NaPTAN data alone have zero independently certified stop-side connectors). Keep same-stop-only boarding or report no verified option until then.
- Integrate current rail data and realtime bus/rail departures, check provider permissions/quotas and timestamp freshness.
- Full Android/PHP end-to-end v2 route/cancel/stop, real Coventry/Bristol cases, cancellation and resource protections.
- 105 production acceptance cases still not independently field approved. No v2 APK or server deployment should be claimed completed.

## Safest immediate continuation
Work on stop-side anchoring, walking-edge provenance and verified transfer geometry, then run an end-to-end Bristol and Coventry test within user-specified walk limits. Do not replace the working v1 router with the currently nonselectable research index.
