# OpenRoad v0.2.9: timetable candidate fairness

The current server router contains v0.2.8 bounded GTFS queries.
In read-only 28 October 2026 live probes, a representative South
Bristol–Clifton journey had 12 walk-budget-compatible transfer pairs
with 10 nearby stops but **zero** with 24. Adding stop choices must not
erase previously valid services.

Cause: a single global LIMIT sampled departures BEFORE validating active
service dates, so extra busy stops crowded out useful trips. The
first-leg expansion limit could also starve entire stop groups.

v0.2.9 patch (private/lib/router.php only):
- Cap schedule departures PER STOP instead of globally.
- Filter for the active service date before per-stop limits.
- Apply the same fairness to destination arrivals.
- Round-robin across origin stop groups before bounded onward-trip expansion.
- Preserve date/time/service filters, route shape, public API, SQL deadlines,
  MySQL schema, device authentication, other server files and Android v0.6.32.

Verified separately:
- Real MariaDB synthetic tests, including extra busy stops:
  https://github.com/bengoodman654/openroad/actions/runs/40737622330
- Read-only staging against current South West dataset:
  https://github.com/bengoodman654/openroad/actions/runs/40738124603
  At approximately 17:42, the live v0.2.8 search with 24 stops found
  zero walking-budget-compatible transfer pairs; staged v0.2.9 found
  23, using ~124 ms of candidate-search time. This is not proof of a
  complete end-to-end itinerary or legal pedestrian transfer connectors.

Deployment uses the exact SHA of the existing v0.2.8 live router,
with one-file atomic replacement, timestamped backup and rollback on
post-install verification failure.

A future controlled GTFS refresh remains necessary: the server dataset
currently contains calendar dates only through 9 November 2026.
