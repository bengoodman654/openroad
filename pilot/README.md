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
