# OpenRoad integrated city planner checkpoint
Date: 29 October 2026. DEVELOPMENT ONLY — Android 0.6.32 and live server v0.2.9 unchanged.

## Source integration completed

Ported the provenance-checked OSM footway graph, independently reviewed stop-side connectors, GTFS city source loader, multi-transfer connection-scan planner, and coordinate-level itinerary adapter onto the current production-based completion branch. The walking bridge rejects unknown GTFS/OSM source hashes, arbitrary nearest-neighbour stop snaps, wrong geometry, too-long walks and disconnected directions. All route results remain research-only and non-selectable because real boarding and endpoint walks remain unverified.

The city loader reads an immutable, verified GTFS SQLite region index OFF HOST. It preserves entire stop-time sequences (no fake express buses when out-of-city stops are clipped), honours boarding/alighting permissions and regional service dates, and enforces bounded searches, cancellations and time limits. It supports up to two transfers/three scheduled bus trips, actual stop-to-stop graph transfers only with approved path evidence, stable source-pinned route IDs and up to three different coordinate-level scheduled alternatives.

## Test results

180 regression tests passed across the integrated city, walking, GTFS, cancellation and coordinate planning modules.
CI: https://github.com/bengoodman654/openroad/actions/runs/40871156441

Official off-host source index from run 40866081561:
- Bristol: 319 selected stops, 10,216 current-date trips, 75,955 bus segments; city snapshot loaded in approximately 1.6–2.5 seconds. Four stop-to-stop scheduled combinations; earliest arrival 18:50 after the 17:45 start, with two transfers.
- Coventry: 436 selected stops, 6,381 trips, 82,990 bus segments; loaded in approximately 1.3–1.8 seconds. Eight stop-to-stop scheduled combinations; earliest arrival 18:08 and one transfer.
- Real coordinate-to-coordinate research, using representative Bristol and Coventry locations, produced three options in each region under both 750m and 900m walking-distance lower bounds. All results unverified for end-point footpaths and non-navigable.
Real index gate: https://github.com/bengoodman654/openroad/actions/runs/40870866363

## Production blockers, not claimed solved

1. Independently checked first/final pedestrian access and physical boarding-side/road crossing access. NaPTAN/OSM matching alone cannot prove a safe path; no real approved stop-side anchors are currently available for this integration.
2. The production PHP server and signed existing Android app do NOT yet execute the new Python research planner. We need a bounded, source-pinned production bridge without compromising JustHostMe, then a same-signed Android release and device verification.
3. Rail integration, live bus predictions, cross-region transit, cancellation in real network conditions, route geometry and complete UI still need field-tested integration.
4. Official fresh feeds are being validated off-host but not yet automatically activated in the live server. The existing calendar-only source is aging; it cannot extend indefinitely.
5. 105 production acceptance cases remain unapproved; passing Python fixtures is not real Android/on-street acceptance.

Next: integrate the verified snapshot engine through a low-resource, signed production endpoint and connect proper walking-access data; do not publish unsafe research itineraries as guidance.
