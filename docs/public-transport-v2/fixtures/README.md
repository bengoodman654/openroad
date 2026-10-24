# Bristol and Coventry reference fixtures — provenance and boundaries

Reviewed 24 October 2026. These records are **published route metadata**, not current vehicle locations or extracted official GTFS calendars.

| Case | Public route | Operator | Published endpoints / key via points | Primary authority |
|---|---|---|---|---|
| BRI-75 | Bristol 75 | First Bus | Cribbs Causeway Bus Station ↔ Hengrove Bus Depot | [TravelWest official journey planner](https://journeyplanner.travelwest.info/service/38-75-_-y10-%25/direction/inbound/timetable) |
| COV-11 | Coventry 11 | National Express Coventry | Coventry ↔ Leamington Spa via Warwick University and Kenilworth | [NX Coventry](https://nxbus.co.uk/coventry/services-timetables/11-coventry-leamington-spa/) and [Warwickshire County Council](https://www.warwickshire.gov.uk/directory-record/7476/11-leamington-spa-kenilworth-university-of-warwick-coventry) |
| COV-12X | Coventry 12X | National Express Coventry | Coventry ↔ University of Warwick | [NX Coventry service index](https://nxbus.co.uk/coventry/services-timetables/) |
| COV-9 | Coventry 9 | National Express Coventry | Green Lane ↔ University Hospital via Coventry | [NX Coventry service index](https://nxbus.co.uk/coventry/services-timetables/) |

Authoritative timetable information changes. These route descriptions are witnesses to the existence of a published service **when reviewed**, not warranties about operation on a future date or time. Refer to the original links for subsequent revisions.

## Fixture layers, which must not be confused

1. `bristol_coventry_reference.json`: independently published names, operator and termini. No invented stop IDs or departure predictions.
2. `tests/pt_v2/test_bristol_coventry.py`: *synthetic* GTFS calendars, stop IDs, trip IDs and times built around those route facts; regression tests only.
3. `tests/pt_v2/gtfs_fixture_adapter.py`: bounded local archive parser (no network). It checks GTFS calendar exceptions, stop order, basic reference integrity and rollover times.
4. `tests/pt_v2/inspect_gtfs.py`: takes an already downloaded ZIP, records checksum and identifies *candidates*, explicitly never production acceptance. Default 8 MiB uncompressed input limit; 1..256 MiB opt-in, only on a separate build runner.
5. `tests/pt_v2/offhost_gtfs_probe.py`: tightly bounded one-shot public GTFS metadata probe on a temporary GitHub runner only; never runs on JustHostMe.

## What is NOT proven yet

- Operator/route IDs and stop IDs from a downloaded DfT dataset
- Timetable departures, calendar and trip validity for an authoritative dated GTFS snapshot
- Mode coverage outside English local buses, real-time monitoring, transfer correctness or rail
- Search of Coventry from Bristol **on Android or the live server**
- Resource benchmarks for production server deployment

## One-shot West Midlands feed test

The isolated GitHub job [run #40075012766](https://github.com/bengoodman654/openroad/actions/runs/40075012766) performed one bounded public-region GTFS download attempt on 24 October 2026. It terminated after the compressed response exceeded **140 MiB**, without retaining a complete archive. No official route/trip rows were parsed. This is **an observed acquisition size failure**, not a failed service lookup and not a production test.

Do not raise that limit simply to force a test through. The next approach should use the DfT BODS timetable metadata API, which permits NOC/operator filtering and links to relevant operator-submitted dataset files. Verify API authorization and response schemas before implementing an operator-scoped importer.

## Requirements and acceptance crosswalk

| Case ID | Fixture/adapter progress | Production acceptance |
|---|---|---|
| COV-01, ID-06 | Published Coventry services and synthetic explicit-place-over-GPS model | NOT RUN |
| COV-02, COV-03, COV-04 | Contract fallback model only | NOT RUN |
| RTE-05, ROUT-02 | Synthetic GTFS after-midnight service-date test | NOT RUN |
| REL-01 | Restricted-scope release-gate model | NOT RUN |

**21 reference contract tests + 20 fixture and inspection tests = 41 passing offline tests.** All **105** acceptance cases remain **NOT RUN / NOT IMPLEMENTED** against the rebuilt transport engine.

## Safety constraints for follow-up

No production writes, no JustHostMe downloads, no secrets in source or logs, no unbounded downloads or decompression, no misleading green test labels. Any real GTFS fixture must have a source URL, retrieval time, SHA-256, service date, operator/agency mapping and independent reference oracle.
