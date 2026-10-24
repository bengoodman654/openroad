# OpenRoad Public Transport v2.2: audited integration contract

Design-only branch. The current OpenRoad Android and PHP production code is unchanged.

Seven corrected vector diagrams, a 56-page authoritative dossier, a correction register for 28 findings, and the complete 105-case acceptance matrix accompany this revision as conversation artefacts.

## Normative design
1. Four independent tasks: journey, service, departure board, map exploration. No journey endpoints for service lookup.
2. Explicit place > selected pin > viewport > GPS **only** when My location was explicitly requested.
3. Assert only licensed, validated provider/mode/area/date capabilities.
4. Stable namespaced operator, line, pattern, trip occurrence and stop IDs; never equate distinct operators by public line number.
5. Pin one immutable schema-compatible timetable snapshot for every complete routing task.
6. Calendar-valid whole journeys; offset-aware UTC events and UK service-date semantics; no automatic relaxation of access constraints.
7. Live/estimated/observed/stale/cancelled are separate states; absent realtime never removes schedules; verified cancelled service is not selectable.
8. Persistent Back arrow at left and X in the right end of the main Where to? field. X priority: dirty-edit confirmation, foreground cancel, visible-guidance Stop confirmation, selected-task close, disabled empty root.
9. Request IDs, generation and pinned snapshot reject all late or mismatched results. Local cancel immediately; remote cancel scoped/authenticated/cooperative; never kill shared imports/workers.
10. Heavy indexing off JustHostMe; signed/staged/validated snapshots, resource gates, atomic switch, rollback and previous-snapshot retention.
11. Release gates cover all enabled P0 cases plus measured shared-host limits and security. A Bristol/Coventry bus pilot cannot claim UK-wide multimodal coverage.

## Test status
The included unittest suite exercises *synthetic reference models* of these rules. It is not an Android or PHP integration test and makes **no external requests**. **0/105 production acceptance cases have passed**. All real golden fixtures, providers, permits and load benchmarks must be verified before enabling any new capability.

See the downloadable v2.2 specification bundle for the complete vector diagrams and 105-row case matrix.


## First real published timetable sample (24 October 2026 milestone)

A 23 October 2026 **Coventry National Express 11** trip, with source operator **TCVW**, approved BODS ZIP hash and 26 ATCO stop codes, has been extracted into the small source-derived fixture at
[Coventry 11 fixture](fixtures/official_coventry_11_friday_2026-10-23_candidate.json).

The limited offline direct-journey reference engine returns University Interchange at **05:55** to Pool Meadow Bus Station at **06:21**. Five calculated checkpoint times agree with a separately published timetable presentation on Bus Times. See [provenance and limitations](fixtures/COVENTRY_11_GOLDEN.md). It is expressly limited to **one trip occurrence on one date**, not a complete route planner.

The new executable tests reject wrong-direction queries, missed departure times, incorrect date/operator/snapshot, unsupported boarding at non-pickup stops, and inconsistent stop times. All test data processing and extraction happen on disposable GitHub runners, not the production server.

**No production acceptance test has passed (0/105).** The prototype is not connected to Android or JustHostMe, and full TransXChange calendar handling, transfer planning, rail, accessible paths, geolocation and server resource benchmarks are still necessary.


## Multi-trip Coventry 11 off-host pilot

The next development stage extends the single known trip to **four actual service dates** (23–26 October 2026). It reads two dated, SHA-pinned official TransXChange revisions off-host, extracts source candidate journeys, and selects up to three direct itineraries where the stop boarding/alighting rules allow them.

Friday's 204 vehicle-journey rows include **102 pairs of exactly duplicated public timetable patterns**. They are grouped for route-choice display without discarding source identities. Saturday has 99, Sunday 62, and Monday 106 candidate journeys. Some non-standard calendars remain excluded and expressly produce partial-coverage warnings.

The preliminary direct-route engine returns results for **Friday, Saturday and Monday**. It declines to calculate Sunday 25 October routes because of the UK daylight-saving clock change, pending source-specific time verification. No weekend or weekday availability claims extend beyond the specifically tested dates.

See [multi-day evidence and limitations](fixtures/COVENTRY_11_MULTIDAY.md) and [machine-readable observed results](fixtures/official_coventry_11_multiday_evidence.json).

The **105 production acceptance tests remain unpassed**: no production Android or server change was made.
