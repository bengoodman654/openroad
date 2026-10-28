# OpenRoad GTFS calendar-only maintenance, 28 October 2026

## Root cause and urgency

South West service_dates ends 2026-11-09. The cached GTFS source
(south_west_gtfs.zip, approximately 182 MB, downloaded 25 September 2026)
contains source calendar dates into 2027, but the active dataset's
service_dates were generated for only the original 45-day window.
The existing cPanel 03:17 nightly full-import cron has not advanced
the active dataset since September and its recent log contains
HTTP-like 404 lines. Its exact root cause is not yet independently
confirmed; no one should claim a new feed has been fetched.

An importer that repeatedly inserts over five million stop_times and
full route shapes would be a poor daily operation on a shared host used
for unrelated websites and email.

## Prepared correction

The new private PHP library maintenance/pt-calendar/calendar_extension.php
and CLI runner maintenance/pt-calendar/extend_service_calendar.php:

- Reads just calendar.txt and calendar_dates.txt from the *already cached*
  181 MB GTFS archive, without extracting routes/shapes/stop_times.
- Applies weekday flags and additions/removals from calendar exceptions.
- Restricts service IDs to trips that already exist in the current dataset.
- Refuses unexpected regions, stale archives older than 60 days, large
  work intervals, more than 60,000 rows, or a dataset switched during work.
- Uses the same private update.lock as the original full importer.
- Writes INSERT IGNORE into or_service_dates inside one transaction only.
- Leaves the router, existing trips, stops, shapes and website/email code
  unchanged.

Synthetic MariaDB tests, including feed exceptions, duplicate-safe
extension and unchanged trip/stop_time tables, passed:
https://github.com/bengoodman654/openroad/actions/runs/40772842061

LIVE READ-ONLY dry run successfully planned **5,750** South West service
date rows from **2026-11-10 to 2026-12-12**, dataset pinned and no writes:
https://github.com/bengoodman654/openroad/actions/runs/40772869060

## Actual installation state

**NOT INSTALLED**. The automated production deployment request was blocked.
Do not infer that or_service_dates has been extended from CI success.
The existing application v0.6.32 and server router v0.2.9 remain usable
for existing calendar dates. The daily read-only freshness guard on main
still monitors expiry.

The one remaining maintenance action is a controlled, authorized
deployment of just the two new CLI maintenance files and their
transactional calendar extension. That action requires an approved
deployment path; do not bypass production safeguards.

Once approved, the old nonworking nightly bulk importer must be
replaced by a low-impact calendar schedule and a separately tested
full-feed refresh workflow built off-host. The existing cached feed
may not include timetable amendments since September; calendars
derived from it must be labelled scheduled-only/stale-source and
must not be treated as independent current service verification.

## Walking transfers and production readiness

The production router currently supports same-stop bus changes.
Validated, directional walking between distinct stops is separately
developed in the pt-v2-planner-hardening branch. It cannot be
enabled for guidance until boarding-side anchors, crossing proof and
OSM topology are verified with reliable provenance. Real public stop
code matching does not prove this.

The 105-case production acceptance manifest is maintained on that
development branch, with all cases pending integrated field verification.


## Safe cron transition after approved installation

The existing full GTFS importer is scheduled for 03:17 daily but does not
advance the active dataset. Its last captured log output ends with cPanel
HTTP-style 404 responses. Do not assume this proves a particular PHP
executable, URL or filesystem mistake without an isolated CLI check.

Once the two new calendar maintenance files have been installed and
verified, the cPanel Cron Jobs entry for the old daily full import should
be disabled. A replacement may run the private CLI calendar extension
at 03:17 each Sunday using the PHP binary that has been verified to run
the script as PHP_SAPI=cli. Do not invoke its PHP file via a public URL,
and do not add any nightly full-data rebuild.

The script fails closed if the cached feed is more than 60 days old or
no longer matches the active dataset's import timestamp, so this is a
temporary window extension, not a perpetual stale-timetable workaround.

The next fully refreshed BODS data must be built and tested separately
from the shared host; only then plan a low-load, versioned replacement
of the existing large timetable dataset, with time/memory limits and a
rollback. Keep the live route planner at v0.2.9 while this is prepared.

The daily read-only GitHub calendar guard on main remains in service.
If it reports seven days or less remaining, that is an urgent pending
maintenance failure; it is not evidence that the automatic extension
ran successfully.
