# OpenRoad Android v0.6.25 — Phase 1 foreground search hardening

Based on the user's v0.6.24 Android source, with no unrelated UI redesign.

## Changed

- 18.5-second native foreground search deadline, covering server calls, local fallback, via-stop routes, and enrichment. A separate 19.5-second JavaScript watchdog handles missing bridge callbacks.
- A per-search delivery gate suppresses duplicate success/timeout callbacks and updates after cancellation. New requests invalidate old results.
- Route-search timings and provider outcomes go to Android Logcat as `OpenRoadTransit`; no GPS positions, API keys or journey paths are logged.
- Transit search progress labels and a prominent retry state replace indefinite loading.
- Slow GTFS downloads/preparation now use a separate background executor; the route executor will not download a timetable or start parsing a cold cache.
- Prepared local fallback is only available if the region's schedule is already parsed into memory; additional cancellation polling occurs during expensive on-device GTFS scans.
- A private server error is retained in the failure message if no prepared local timetable is available.

## Important limitation

This phase does NOT add a national rail timetable planner. The current server's BODS regional bus graph cannot produce Bristol–London train journeys. Rail Data Marketplace LDB is for live enrichment, not national timetable routing. Phase 2 must add national railway timetable scheduling and London interchange planning.

## Checks executed

- `bash validate.sh`: passed
- `node --check app/src/main/assets/app.js`: passed
- Standalone `TransitSearchGateTest.java`: passed (200 concurrent delivery/expiry race trials)
- UI watchdog vm tests: passed (deadline, stale request, preserved results)

An Android SDK/Gradle build, signed APK, real-phone testing and live-server latency measurements were not available here, so these are source-level checks only. Server v0.2.3 upgrade is separate. Do not deploy the full server source in place of the private config.
