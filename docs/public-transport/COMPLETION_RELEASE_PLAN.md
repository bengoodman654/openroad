# OpenRoad completion release — one integrated app
**Baseline:** 29 October 2026. Branch created from current production main: Android 0.6.32, server router v0.2.9.
**Objective:** Normally signed, stable OpenRoad update covering driving, cycling, walking, bus and rail. **Status: NOT RELEASED.**

## Principle: integrate forward without undoing working fixes

The pt-v2-planner-hardening branch is valuable but its original staged Android and PHP integrations were based on older v0.6.31 and v0.2.5 archives, respectively. Adapt and test individual modules on the current working sources, not by merging old source ZIPs. Keep working bus routing, signing identity and current website/email hosting unchanged.

## M1 — Durable, automatically refreshed schedules

- Repair/replace the ineffective 03:17 daily full GTFS importer. Calendar-only service-date extension is live and verified through 13 December 2026 but uses the September feed; it cannot reflect subsequent timetable revisions.
- Acquire and preindex current South West and West Midlands GTFS feeds OFF the JustHostMe shared host. Install a source-pinned, size-bounded, low-impact, rollback-capable refresh pipeline. Preserve service exceptions and provenance; monitor expiry and feed age.
- Verify real Bristol and Coventry dated direct/transfer itineraries against each published feed. Distinguish stale, unavailable and no-journey.
PASS: both regions' latest applicable service calendars are correctly refreshed without overloading the shared hosting account.

## M2 — Production bus and walking journey planner

- Integrate bounded connection scanning, one or two transfers, up to three meaningful alternatives, GTFS stop order, pickup/dropoff permission, time zones, late-night GTFS times, walking limits, via-stops and cross-region logic.
- Use directional connected pedestrian geometry for transfers between separate stops. Do not invent straight-line footpaths or claim verified crossing/stop-side accessibility from NaPTAN↔OSM identity proximity alone.
- Stabilise itinerary IDs and ensure later predictions cannot change the explicitly chosen option.
PASS: installed app reproduces real Bristol/Coventry journeys with correct stops, sensible change times, bounded response times and no false absence or fabricated walking connectors.

## M3 — Rail, realtime, cancellation and UI

- Integrate the actual server-side bus/rail data accounts and licences. Rail-first for long journeys; bus-to-station and onward walking links; honest unsupported-region/provider outcomes.
- Distinguish live departures from timetable-only, expired predictions and quota limits; never label a stale prediction as live.
- Finish authenticated Android–PHP task issue/route/cancel/status and cooperative worker termination without interrupting another task.
- Preserve the Back arrow and X inside Where to? throughout public-transport screens, separate search cancellation from active guidance, keep map camera stable, show usable route cards and stops.
PASS: real paired-device/network/worker tests; no ghost guidance, silent route switches or unusable error handling.

## M4 — One signed release and real-world acceptance

- Integrate on THIS branch, with existing current Android and PHP source files. Preserve drive, cycle and walk paths and updater package/signing configuration.
- Run source compilation, PHP/MariaDB, JavaScript UI, source-pinned GTFS/OSM, load, cancellation, data expiry, security and offline/error tests. Use the 105 named acceptance cases as traceable coverage; do not count synthetic tests as real field passes.
- Publish through the existing normal signed Android update mechanism, not a second debug app.
- Verify on the actual Fairphone and live server: Bristol direct and transfer; Coventry local bus; rail; walking transfers; search, route selection and cancellation; return appropriate responses for unavailable data.
PASS: independently witnessed expected results, repeatable end-to-end, and rollback ready.

## Outstanding external dependencies and safeguards

- No new passwords or signing material should be copied into chat.
- Rail/transport source permissions and UK-wide coverage must be checked against actual connected server provider entitlements, not assumed.
- Pedestrian stop-side/crossing access cannot be field certified by code alone. Mark uncertainty and refuse unsafe unverified transitions.
- User provides real phone and on-street checks only when unavoidable; ordinary source integration and testing does not require manual inputs.
- Never make an unsupported claim of 105/105 passing, national coverage, 20-second real-world SLA, accessibility certification or production readiness.

## Immediate action
Audit released 0.6.32 Android + installed v0.2.9 server sources; repair the stale feed pipeline first; then integrate the planner and cancellation end-to-end. Leave current normal app functional while the unified release is prepared.
