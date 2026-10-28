# OpenRoad PT v2 — scheduled-bus pilot (research only)

This isolated Python prototype was built from the approved v2.2 public-transport design. It does **not** modify the existing Android application, shared-hosted transport server or automatic updater. It uses the Python 3 standard library only.

## Scope

- Parses official DfT Bus Open Data Service (BODS) regional GTFS archives as streamed ZIPs.
- Selects a chosen service date, applying weekly calendars and `calendar_dates.txt` exceptions.
- Restricts the pilot to a 15-km radius around Bristol or Coventry, and to GTFS `route_type=3` buses.
- Maintains distinct source route, trip and stop identifiers (not just public bus numbers).
- Constructs scheduled stop-to-stop connections and a simple one-earliest-arrival connection-scan search with configurable transfer buffers.
- Checks boarding/alighting permissions, hard transfer limits, late-night 24+ times and DST time conversion.
- Provides explicitly **approximate** first/last-mile walk distances, not verified pedestrian paths.
- Builds a compact, release-pinned SQLite index using integer keys. Dataset preparation belongs on an external builder, never on the user's shared host during a search.

**This is a deliberately limited research engine.** It cannot be used as the production public transport planner until the wider v2.2 release gates pass.

## Official input datasets

- Coventry: https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/west_midlands/
- Bristol: https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_west/
- GTFS semantics: https://gtfs.org/documentation/schedule/reference/

Download each ZIP to a *temporary folder outside the repository*. The ZIPs are large. Do not commit them or any API keys.

## Execute

Requires Python 3.11+; no third-party packages.

Synthetic tests (no downloads or server access required):

    python3 -m unittest discover -s pilot -p 'test_*.py' -v

Real-data, read-only integration probe:

    python3 -m pilot.gtfs_engine \
      --west /path/to/west_midlands_gtfs.zip \
      --south /path/to/south_west_gtfs.zip \
      --date 2026-10-26

This prints two JSON records: source inventory and one independently reconstructed *within-feed* sample itinerary per city. The sample oracle compares the search with a feasible trip from the **same** published feed; it is not independent corroboration by an operator.

For an off-host builder, call `populate_sqlite(snapshot, sqlite_connection)` with an empty SQLite database. Never run a heavy GTFS import interactively on the shared host. Release/promotion requires separate integrity, licensing, size and performance checks.


Version-pinned real-data verification (four stored oracles: direct and transfer in each city):

    python3 -m pilot.verify_real \
      --west /path/to/west_midlands_gtfs.zip \
      --south /path/to/south_west_gtfs.zip

This checks the SHA-256 hashes of the original archives, exact trip IDs, service lines, change stops, scheduled arrival times and SQLite connection counts. When BODS publishes a newer archive, this test must fail until a new validated fixture is recorded.

## Experimental stage 4: walking transfers and journey alternatives

`journey_options.py` implements a separate, bounded multi-label scheduled journey search. It accepts **explicit directional pedestrian links**, specified in metres and seconds, and can keep feasible journeys with different time/change/walking trade-offs. It does not infer walkable roads from nearby straight-line coordinates.

Example for a data loader or external path router:

    from pilot.journey_options import Footpath, journey_options
    result = journey_options(snapshot, "STOP_A", "STOP_D", 8 * 3600,
        footpaths=[Footpath("STOP_B", "STOP_C", 120, 120, verified=False)],
        max_walk_m=800, max_transfers=2)

Walk links that have not been independently checked must retain `geometryValidated: false` and the warnings `UNVERIFIED_WALK_GEOMETRY` and `NO_ACCESSIBILITY_PROOF`. The search has a bounded horizon and label budget; an exhausted budget returns `SEARCH_LIMIT`, **never** `NO_JOURNEY`.

This is not a vetted national Pareto journey planner, and there is no production-grade pedestrian graph or geographic stop matching. The existing `plan_stops` baseline is retained unchanged. GitHub Actions runs the existing 23 synthetic cases and the new independent transfer/alternative assertions.

## Test evidence

See [real-feed-evidence-2026-10-26.json](real-feed-evidence-2026-10-26.json) for the exact feed versions, SHA-256 hashes, route examples, measured local index sizes and executed-check counts.

## Unimplemented / blocking work

- The 105 v2.2 production acceptance cases are **not** marked passed.
- A one-best-arrival scanner is not yet a robust multicriteria / Pareto journey planner.
- No full map-matched pedestrian graph, intermediate walking transfer graph or wheelchair-accessibility proof.
- No cross-region routing, national rail graph, realtime predictions, verified disruptions, identity crosswalk to NaPTAN, fares, complete bus-operator coverage audit, provider licences per feed, or multi-day journey enquiry.
- No API request lifecycle, authenticated server cancellation/tombstones, concurrency tests or actual shared-host safety measurements.
- No end-to-end 20-second SLA proof, Android UI tests or field validation.
- Regional geometry is clipped. A service going outside the test radius may not be routable through its full journey; such a route is not fabricated.

No files in this pilot should be deployed or executed on the live server without further review.

## 26 October 2026: first multi-option correctness hardening

The original proof-of-concept scanner (`plan_stops`) remains as a historical
single-best-arrival comparison. The **separate** `journey_options` module is
now the more capable research pathfinder:

- Scans each dated GTFS connection once, rather than expanding every trip
  into every possible boarding/alighting pair. Stop and onboard states are
  maintained separately.
- Enforces a configurable minimum interchange time (default 120 seconds);
  staying aboard the same physical trip does not incur this buffer.
- Holds multiple non-dominated labels, considering earliest arrival, number
  of boardings, total walking and readiness to board.
- Returns up to three **meaningful Pareto trade-offs**, when they exist; it
  does **not** yet guarantee three diverse routes when alternatives have equal
  criteria, or claim to be the final production journey ranker.
- Handles intermediate walks only through **explicit, directional footpath
  edges** supplied by a separate pedestrian router. A `verified=True`
  geometry flag **never** implies accessibility, step-free provision or live
  obstruction-free access.
- Applies hard walking, transfer, time-horizon and state-label bounds. A
  label-budget failure is reported as `SEARCH_LIMIT`, not `NO_JOURNEY`.
- Preserves original GTFS `stop_sequence` values in the in-memory and SQLite
  connection index. The parser accepts legal non-consecutive sequence values,
  but never joins stops across omitted/out-of-radius intermediate events
  (including when circular trips revisit the same stop).

**Regression status:** 44 deterministic synthetic tests passed in the
isolated Python test runtime on 26 October 2026. A single artificial
100,300-connection scan returned a valid one-bus journey in approximately
0.067 seconds on that runtime. It is **not** a measured shared-host response
time, production RAM benchmark or representative network latency.

**Real-feed baseline caution:** the four within-feed Bristol/Coventry checks
and recorded SQLite sizes in `real-feed-evidence-2026-10-26.json` were
obtained on the **earlier** parser. The corrected `stop_sequence` semantics
can change the total indexed connection count, and adding sequence metadata
changes SQLite size. These measures and the four source-pinned integration
tests **must be rerun** with the exact source ZIPs before any release gate is
advanced. No acceptance criteria have been marked passed for production.

### Still blocked for production

The footpath provider, pedestrian topology, mobility/accessibility treatment,
route-diversity algorithm, realtime integration, regional boundary handling,
rail planning, complete stop/source crosswalk, provider rights, cancellation,
Android UI, shared-host memory/load, security and field validation remain
unimplemented or unproved. Keep this branch isolated from both production
apps and the hosting account.


## 26 October 2026 — pedestrian topology prototype (not field validated)

`pedestrian_graph.py` is an additional **OFF-HOST** research module.
It creates a directional walking network from consecutive, shared OSM node
identities; geometric lines that cross without sharing a real node are **not**
joined. It checks tagged walking permissions and pedestrian-only one-way
restrictions, blocks known barrier nodes, and rejects missing or misleading
topology. It has a step-avoidance option but does **not** assert wheelchair
accessibility (kerbs, widths, dropped crossings, surfaces and obstructions are
not independently checked).

Crucially, **GTFS stops are not automatically snapped to pavements**.
`propose_stop_anchors` generates *non-routable*, explicitly unverified
candidate graph nodes. To make a stop usable, an independent validator must
supply a `StopAnchor` with checked, directional pavement-side access,
provenance and a geometry that actually reaches both endpoints. If there is
no verified connector, the search must not invent one.

Given those vetted connectors, `link_stops` computes an actual graph route
and returns a directional `Footpath` containing its original geometry,
travel distance/time, source name, source snapshot hash, mapped steps and a
geometry confidence flag. `journey_options` can now carry this geometry into
its WALK legs for future Android rendering. The flag says the supplied
network *geometry* is continuous; it **does not** mean the real-world route
has been surveyed, is currently open or is accessible to all users. Road
centre-line approximations are flagged as unverified.

### Build inputs and licensing

The optional loader `load_osm_pbf_offhost` uses `pyosmium` and expects a
small, reference-complete geographic `.osm.pbf` extract. Prepare such
extracts on a proper development computer/build worker using Osmium's
`extract --strategy complete_ways`, with a surrounding buffer to include
way nodes at the city boundary. Do **not** load large OSM PBFs, run graph
generation, download fresh extracts or calculate inter-stop footpaths on
the shared JustHostMe server. The first city-scale PBF imports have
since run successfully on isolated GitHub runners (see the dated
reconnaissance report below). The Bristol/Coventry ground-truth stop-side
link audit remains a release blocker.

The OpenStreetMap database is ODbL-licensed. Attribution and any applicable
derived-database sharing obligations must be handled before public release:
- https://osmfoundation.org/wiki/Licence/Attribution_Guidelines
- https://osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ
- https://docs.osmcode.org/osmium/latest/osmium-extract.html
- https://docs.osmcode.org/pyosmium/latest/user_manual/03-Working-with-Geometries/

### Proof status

**67 deterministic synthetic tests passed in the isolated runtime on
26 October 2026** (the previous 44 plus 23 new pedestrian/geometry safety
tests). These include nearby but disconnected stop pairs, no imaginary road
crossings, pedestrian one-way rules, steps, blocked barriers, excessive
detours, impossible or unverifiable stop connectors, truthful route geometry,
provenance and walking warnings. The real OSM PBF import was subsequently
tested as described below; independently checked Bristol/Coventry stop access,
fresh GTFS full integration, shared-host capacity, cancellation and Android
integration remain **unverified**.

**Production acceptance remains 0/105; no deployment is authorised by this
research result.**

The isolated `osm-smoke` CI job additionally installs pinned pyosmium
4.3.2 and parses a tiny reference-complete **OSM XML** fixture, checking
node coordinates, access filtering, barriers and source hashing. This tests
the parser adapter independently of city-sized `.osm.pbf` import. The
separate real-data run subsequently ingested both Bristol and West Midlands.


## 26 October 2026 — first actual Bristol/Coventry OSM reconnaissance

A one-off, explicitly gated GitHub Actions workflow downloaded official
Geofabrik **Bristol** and **West Midlands** OSM PBF extracts to temporary
GitHub runners. The pilot parsed walking networks within **2.5 km of each
city centre**. Source file hashes and both reports are preserved in
[`real-osm-evidence-2026-10-26.json`](real-osm-evidence-2026-10-26.json).

| Diagnostic quantity | Bristol | Coventry |
|---|---:|---:|
| Walking-network nodes | 30,087 | 17,833 |
| Directed walking edges | 62,940 | 37,002 |
| OSM bus-stop nodes | 391 | 436 |
| OSM stops with an **unverified** graph-node candidate within 40 m | 361 | 390 |
| Connected nearby stop-pair graph trials (out of 40) | 31 | 17 |
| Trials with no bounded graph path (out of 40) | 9 | 23 |

These 40 pairs are deterministic, **not randomly selected** and are not a
city-wide coverage sample. A connected route in this table only means the
proposed *graph nodes* are connected; it does **not** validate foot access
between the real boarding points and graph nodes. Some included road centre
lines are explicitly labelled as approximate. Conversely, a rejected route
might reflect incomplete OSM mapping or a conservative tag filter.

OSM stop tags include 382 candidate Atco codes in Bristol and 433 in
Coventry, but **none has yet been independently cross-checked against the
real GTFS stop identifier, pavement side, crossing or entrance**. This must
happen before these routes can be offered to people. Zero of the 105
production acceptance criteria are passed.

The one-off workflow:
https://github.com/bengoodman654/openroad/actions/runs/40392894775

Both the real-data probe and the separate synthetic-regression workflow
completed successfully. No PBF files were committed to GitHub, and neither
the Android app nor the live shared server was touched.


## 27 October 2026 — interrupted-work recovery

The initial 27 October local commit was not pushed owing to unavailable
command-line GitHub credentials. These improvements were reconstructed
and committed through the connected GitHub API on the isolated branch.

- A strict ATCO-code identity audit counts exact nearby matches separately
  from missing, distant or duplicate matches; it deliberately creates
  **zero verified pedestrian stop connectors**.
- Invalid geometry in unverified as well as verified walking legs now fails
  closed, before the map can display it.
- Four real timetable oracles retain their exact DfT source SHA, trip IDs,
  service date, bus lines and scheduled arrival. The historical old-parser
  connection counts are retained only as baseline measurements.
- The multi-option planner must independently reproduce the same physical
  bus trips and arrival. A different interchange stop is allowed only
  when the same trips meet at that stop with the mandatory transfer time.

The previous offline session reported exact, unique, nearby stop-code matches
for 299/339 Bristol and 354/383 Coventry city-centre GTFS stops. The
counts are stored in stop-crosswalk-observations-2026-10-27.json and
explicitly labelled as recovered **unrerun** observations, not ground truth.

The recovered testing does not establish pedestrian boarding access, current
closure status, accessibility or production acceptance. Keep the Android app,
deployed PHP, main branch and shared hosting unchanged until the 105 production
cases have been evaluated.


## 27 October 2026 — independent real-data rerun completed

Both city audits succeeded on disposable GitHub runners: https://github.com/bengoodman654/openroad/actions/runs/40592636211

- Bristol: 339 GTFS stops examined in the 2.5 km pilot; 299 exact unique nearby ATCO matches, 4 distant, 36 unmatched.
- Coventry: 383 stops examined; 354 exact unique nearby matches, 15 distant, 14 unmatched.

Both match the numbers retained from the interrupted research session. Full machine-readable logs, current OSM and pinned GTFS SHA-256 source hashes, and review examples are retained in real-stop-crosswalk-evidence-2026-10-27.json. These are exact-code identity findings **only**. Zero walking anchors were approved for routing, and the Android, server and production acceptance status have not changed.


## 28 October 2026 — cancellable search contract and source integration map

See [cancellation-and-response-gate](../docs/public-transport-v2/CANCELLATION_AND_RESPONSE_GATE.md) for the tested standalone task lifecycle, cancel-before-registration tombstones, client-generation fence, independently checked timetable legs, and exact Android/Java/PHP integration points discovered in the source archives. All remain research-only; no live software was altered.


## 28 October 2026 — cross-language request lifecycle fixtures

The isolated pilot now contains a JavaScript screen-state reference
(pt_v2_screen_state.js), a PHP signed-ticket/file-lock cancellation
reference (php_v2_cancellation.php) and a Python research response envelope
with stable journey IDs. Their separate tests are included in the
PT v2 GitHub workflow.

Latest verified run:
https://github.com/bengoodman654/openroad/actions/runs/40692720487

Python: 143 discovered / 142 passed / 1 optional skipped.
JavaScript: 12 checks passed. PHP: all reference checks passed.
These are research checks, NOT the 105 required production acceptance cases.
No live Android/server source, packages or credentials changed.


## 28 October 2026 — actual archived source staging

The first exact Android v0.6.31 and PHP v0.2.5 integration staging packages, CI evidence and production blockers are documented in [the integration status report](../docs/public-transport-v2/SOURCE_INTEGRATION_STATUS_2026-10-28.md). These packages are RESEARCH ONLY. No main-branch release, phone update, shared-host deployment or remotely cancellable PHP worker is claimed.
