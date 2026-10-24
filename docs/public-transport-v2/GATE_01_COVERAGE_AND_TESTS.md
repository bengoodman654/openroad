# OpenRoad Public Transport v2 — Gate 01: Coverage, identity and safe failure

Status: DESIGN / TEST FIXTURES NOT YET EXECUTED  
Prepared: 24 October 2026  
Baseline: OpenRoad PT v2.2 authoritative design (23 October 2026)  
Repository baselines: Android v0.6.31 source archive; Transport Server v0.2.5 source archive  
Target pilot: Bristol and Coventry English local buses. Scope is conditional on data rights, real feeds and fixture validation.

## 1. Goal and release boundary

Prove that public transport search has actual, date-valid and legally usable data for the requested mode and area BEFORE claiming that an empty search means no services run. Keep v1 production, the installed Android build and the shared host unchanged until acceptance gates pass.

Four independent functions remain: (a) journey planning; (b) service/route search; (c) stop/station departures; (d) map exploration. A capability may be enabled for one without implying that the others work. Live updates are optional enrichment.

No production acceptance criterion in this document is marked passed. The 20 pure reference checks described in v2.2 do not count as Android/server/data acceptance.

## 2. Source readiness register (initial research, not authorisation proof)

| Source | Proposed use | Verified public scope | Gate still open |
| --- | --- | --- | --- |
| DfT BODS TransXChange | English local bus timetables, journey graph, line/patterns | Timetable datasets are available for consumer use; English local bus scope | Actual Bristol and Coventry feed versions, validity, missing operators, quality tests, source-specific terms |
| DfT BODS SIRI-VM | Bus positions/vehicle monitoring | Centralised English bus AVL consumer service | Request format, credentials, live join confidence, health, quota and age thresholds |
| DfT NaPTAN | Stop IDs and coordinates | England/Scotland/Wales stops; OGL | Dataset snapshot, decommissioned stops, accessible quays and stop-to-trip joins |
| National Rail Darwin/LDB | Rail departures, changes and platform predictions | Public live feed through Rail Data Marketplace | Account-specific entitlement, usage limits and trip joins; NOT a complete journey graph |
| Network Rail SCHEDULE | Published rail schedule foundation | CIF/JSON daily schedule feed, registration subject to terms | Account/feed rights, calendar conversion and connecting journey-graph proof |
| National Rail RTJP/OJP | Optional point-to-point rail planner | Separate formally licensed service; access transition expected November 2026 | Licence, charges and API access; do NOT enable before entitlement |
| TfL and other nations | Additional bus, tram, metro, rail modes | Not established by the above English BODS proof | Source-by-source licence, region, date, service and journey capabilities |

Official research:
- https://www.gov.uk/guidance/find-and-use-bus-open-data
- https://www.gov.uk/government/publications/technical-guidance-publishing-location-data-using-the-bus-open-data-service-siri-vm/technical-guidance-siri-vm
- https://naptan.dft.gov.uk/
- https://www.networkrail.co.uk/who-we-are/transparency-and-ethics/transparency/open-data-feeds/
- https://www.nationalrail.co.uk/developers/darwin-data-feeds/
- https://www.nationalrail.co.uk/developers/online-journey-planner-data-feeds/

The source register is provisional. Do not equate an openly described service with a verified individual dataset or permission to redistribute every derived product.

## 3. Capability manifest — required before a task can run

Each independently tested dataset snapshot must include:

- snapshotId, schemaVersion, producer, createdAt, content hashes, signature/integrity status, supported client schema range
- providerId, feed ID/version, source licence reference, attribution, allowed uses, credentials held server-side, last verified rights date
- mode(s), polygons/areas and supported task capabilities (journey, service, departures, map, realtime)
- full service-date interval, calendar exceptions, snapshot publication/expiry, accepted older-snapshot policy
- stop/operator/service/pattern/trip/vehicle namespace mappings and identity quality, including original ATCO/NaPTAN/CRS/GTFS/TransXChange IDs
- graph readiness: walking connectors, transfer edges, cross-region shards and accessibility evidence (TRUE/FALSE/UNKNOWN)
- health/quality state and known gaps; measured snapshot size; maximum compatible query budget

A capability is ENABLED only when rights, date range, identity, graph/lookup completeness and validated snapshot requirements all pass. A task may be disabled without disabling the other tasks.

Suggested statuses: VERIFIED_READY, DEGRADED_COMPATIBLE_SNAPSHOT, ABSENT, EXPIRED, INVALID, UNLICENSED, INCOMPATIBLE.

**No GPS fallback override:** resolve explicit chosen city/stop > chosen pin > map viewport > GPS only after the user selects My location. Search Coventry while physically in Bristol must search Coventry.

## 4. API response invariants

Envelope fields: requestId, generation, operationId, taskType, snapshotId, schemaVersion, outcome, reasonCode, coverage, provenance, timeBasis, validUntil, results, warnings, nextActions, realtimeStatus, serviceStatus, remoteJobStatus.

Independent axes:
- outcome: OK, PARTIAL, NO_MATCH, NO_JOURNEY, COVERAGE_MISSING, PROVIDER_UNAVAILABLE, TIMEOUT, RATE_LIMITED, INPUT_INVALID
- realtime: SCHEDULED_ONLY, PREDICTED, OBSERVED_FRESH, LAST_KNOWN, UNAVAILABLE
- service: SCHEDULED_UNVERIFIED, OPERATING_REPORTED, DELAYED, VERIFIED_CANCELLED, DIVERTED, UNKNOWN
- remote job: RUNNING, CANCELLED_LOCALLY, STOPPING, STOPPED, UNKNOWN

An empty results array is never the sole failure indicator. A scheduled valid result survives absence of live data. A verified, correctly identified cancellation marks the specific affected trip unusable; keep its explanation and request confirmation before changing active guidance.

A visible result is selectable only if its full itinerary, calendar, hard walking/accessibility constraints, transfer buffers, trip IDs and pinned snapshot have all been validated. Later enrichments cannot change itinerary identity, selection or map camera.

## 5. Synthetic deterministic fixtures: initial tranche

All example IDs below are invented TEST IDs — not real bus operators, stops or trips. Each scenario requires a committed input fixture, exact expected response, runner and evidence file before it may pass.

| Test ID | Synthetic setup / injected failure | Required oracle |
| --- | --- | --- |
| SRC-01 | Coventry selected, phone GPS Bristol; Coventry bus catalogue VERIFIED_READY | Search area remains Coventry; Bristol results must not substitute |
| SRC-02 | Coventry bus catalogue ABSENT, return empty candidate list | outcome=COVERAGE_MISSING with missing feed/region reason, not NO_JOURNEY or NO_MATCH; no interactive full import |
| SRC-03 | Darwin departures available but rail planner/schedule graph unavailable | Rail board enabled if valid; rail A–B planner capability disabled with explicit source limitation |
| ID-01 | Two test operators each publish line 75, identical public number, different direction and source IDs | Two distinct selectable service identities; no number-only joins |
| ID-02 | One operator line 75 with two branches and a short working | Pattern-specific stop order and valid service-day trip occurrence preserved |
| ROUT-02 | Test journey has a 25:10 departure from its timetable service day | UTC instant and next-calendar-day clock time resolve correctly; service day retained |
| ROUT-03 | Europe/London spring/fall DST transition test days | Unambiguous offset-aware instants; ambiguous or nonexistent local inputs handled by explicit policy |
| DATA-02 | A–B journey traverses two synthetic regional shards with differing graph snapshot IDs | No mixed-epoch itinerary; compatible pinned epoch or COVERAGE_MISSING/INCOMPATIBLE |
| LIVE-06 | Valid test bus schedule, upstream SIRI-VM returns 429 or times out | Same scheduled itinerary remains selectable; realtimeStatus=UNAVAILABLE; no invented cancellation |
| LIVE-07 | Signed verified cancellation matches exact tripOccurrence/date/stop and source | Only affected occurrence unusable; explanation + alternative; active guidance not silently replaced |
| UI-09 | First complete validated result selected; delayed second/third alternatives arrive | Selected immutable itinerary ID and map camera remain stable |
| CAN-07 | Existing guidance; user searches different service and presses top-right X | Cancel foreground lookup only; original guidance continues |
| CAN-11 | X sent before remote job registration; server admits late job | Atomic authenticated task tombstone blocks execution; cancelled generation cannot update UI |
| CAN-13 | Two users subscribed to same shared fetch; one cancels | Only first subscriber detached; second fetch still returns; builder/cache survives |
| OFF-01 | Offline schedule exists but pedestrian paths/map bundle do not | No claim of complete offline guidance; show available timetable with stated limitations |
| REL-01 | Bus pilot tests pass but rail licence/graph absent | Only proven Bristol/Coventry bus capabilities may be enabled; no UK-wide multimodal promise |

Additional tests must link back to the complete 105-case matrix in v2.2. No synthetic pass satisfies a real-feed Coventry or Bristol acceptance gate.

## 6. Android control rule carried forward

Persistent left Back arrow and top-right X inside 'Where to?' (no separate lower Stop). X priority: (1) foreground task cancels it without stopping guidance, (2) otherwise viewing guidance prompts Stop, (3) otherwise selected idle PT result closes, (4) empty PT root X disabled. Back pops exactly one screen, stops only owned child lookups and never silently ends guidance. Dirty route edits require Keep editing/Discard; committed route remains untouched.

Cancellation owner hierarchy: sessionId -> taskId -> subrequestId, each with generation and immutable snapshot reference. Client immediately invalidates results and aborts local work; authenticated remote cancellation is cooperative and idempotent. Shared data builders and unrelated requests are never terminated. Server status is STOPPED only with evidence; otherwise STOPPING or UNKNOWN until a lease expires.

## 7. Proof required to exit Gate 01

1. Real Bristol and Coventry BODS catalogue inventory, date-specific TransXChange quality, operator/stop coverage and source licence record retained.
2. NaPTAN identities successfully join to representative real stop sequences, branches, service calendars, and operating/non-operating dates.
3. Small canonical snapshot built OUTSIDE shared hosting, with content hashes, local indexes and date/area capability manifest; no on-demand interactive imports.
4. A deterministic test runner checks the listed fixtures against the actual contract and stores exact expected/actual IDs and statuses.
5. At least one genuine Coventry local journey and one Bristol journey are verified through real imported timetable data, with a known service-date/time oracle.
6. Proven safe cancellation and cross-request isolation, including cancel-before-registration.
7. Shared-host resource limits measured under representative concurrent website/email load, thresholds documented and automatic fail-closed admission/rollback tested.
8. Every release-scope P0 plus security tests pass; unsupported modes remain explicitly disabled.

Latency objective from user requirements: first complete usable result within 20 seconds, if coverage and a feasible journey exist. Instrument request start, capability lookup, query, first complete result and cancellation. Never manufacture an infeasible route just to hit the deadline.

## 8. Explicitly deferred

- Any claim of UK-wide bus/rail/tram routing.
- Rail A–B route output until real schedule/graph or RTJP rights and access are verified.
- Use of Darwin as a substitute for a complete rail routing graph.
- Arbitrary hosting CPU/RAM/SQL quotas before baseline measurement.
- Altering production Android, server settings or source release archives.

Next working step: prepare the real Coventry/Bristol source inventory and canonical small fixture; then turn the initial synthetic cases into executable assertions while preserving the unchanged v1 release.
