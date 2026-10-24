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

Do not raise that limit simply to force a test through. Smaller official operator-scoped BODS metadata and ZIP files were obtained instead, with the BODS key remaining on the production server and all substantial XML processing taking place on disposable GitHub runners.

## Verified real official dataset acquisition

**Coventry:** BODS operator NOC `TCVW` returned an authorised metadata page containing dataset **20442**, modified 19 October 2026. Its public 11,172,224-byte ZIP is pinned to SHA-256 `5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0`. All **38 TXC XML members** were processed with a bounded-memory streaming parser, confirming in-file NOC `TCVW` and line names **9, 11 and 12X** in their own XML members. The 321,777,152-byte declared expanded total was **never extracted into a directory**. See `official_coventry_txc_manifest.json` and [the successful full streaming audit](https://github.com/bengoodman654/openroad/actions/runs/40079491063). These observations validate source identity, **not** date-specific trip selection or passenger journey correctness.

**Bristol:** The full `FBRI` metadata response contains 35 datasets. Five advertise service 75. Four sources' **inspected service-75 XML members** proved to be Ipswich (`FECS`), Colchester (`FESX`), York (`FSYO`) or Hunslet (`FLDS`). They must not be used as Bristol route 75. The fifth dataset, **18422**, remains unresolved because the conservative filename selector found no 75-labelled members. Do **not** infer that uninspected XML members contain no Bristol routes. See `official_bristol_candidates.json` and `official_bristol_negative_sources.json` for the exact source hashes, URLs and limits.

**Mandatory source acceptance gate:** A route-number match and even a BODS operator-group metadata NOC are insufficient. Verify the **service-bearing XML member's** own National Operator Code, the exact operator identity, the route's ATCO/NaPTAN stop pattern and geography, its service calendar and its trip times against an independent oracle before approving the input to a journey planner.

All substantial downloads and XML processing were off-host. JustHostMe executed only bounded, one-shot *metadata* GETs using its existing private key; no Android or deployed PHP files changed.

## Next real-engine fixture work

1. Extract a compact, version-pinned golden dataset for one confirmed Coventry service, including TransXChange calendar, service-day rules, ordered stops, route and trip identities, and departures.
2. Select Bristol route 75 by the official `FBRI` and `PH0000132` operator/registration plus Cribbs Causeway–Hengrove stop references, **not merely the string “75”**. Probe only bounded source members.
3. Test actual origin/destination queries and re-check against a separately published timetable. Validate server memory/time budget before enabling a production transport API.
4. Only then increment production acceptance test counts. The real Android and PHP integration suite remains **0/105 passed**.

## Requirements and acceptance crosswalk

| Case ID | Fixture/adapter progress | Production acceptance |
|---|---|---|
| COV-01, ID-06 | Published Coventry services and synthetic explicit-place-over-GPS model | NOT RUN |
| COV-02, COV-03, COV-04 | Contract fallback model only | NOT RUN |
| RTE-05, ROUT-02 | Synthetic GTFS after-midnight service-date test | NOT RUN |
| REL-01 | Restricted-scope release-gate model | NOT RUN |

The offline unit suite has expanded since the original 41-test run; consult the latest GitHub Actions log for the current count. The **105 production acceptance cases remain NOT RUN / NOT IMPLEMENTED** against the rebuilt transport engine.

## Safety constraints for follow-up

No production writes, no JustHostMe downloads, no secrets in source or logs, no unbounded downloads or decompression, no misleading green test labels. Any real GTFS fixture must have a source URL, retrieval time, SHA-256, service date, operator/agency mapping and independent reference oracle.
