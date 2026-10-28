# OpenRoad SQL 3024 bus timetable repair

The South West regional GTFS table contains ~5.85 million stop times; a
read-only JustHostMe check verified 181 active service IDs for 28 Oct 2026
and service dates through 9 November 2026.

Existing MariaDB statement limits: fast 3s, full 4.5s. Keep them.
The old queries expand stop-times self-joins before SQL LIMIT; full phase
always attempts transfers even when a valid direct journey exists.

Only private/lib/router.php is changed: bounded index-backed departure/
arrival candidate searches, per-trip PK stop lookups and transfer search
only if no valid direct candidate was identified. The v1 public PHP endpoint,
device signature checks, SQL schema, live BODS gateway and Android app are
unchanged.

Test evidence: https://github.com/bengoodman654/openroad/actions/runs/40714767173
Real MariaDB fixture tests cover direct, connecting, inactive service,
response shape, and existing router PHP checks.

Deployment checks original live SHA matches versioned v0.2.5 source.
It backs up live router.php before atomically replacing a single PHP file,
validates SHA and PHP lint afterward, and attempts rollback on any failure.
A complete 5.85M-row live route search has not been executed in CI.
The user should test South Bristol to Clifton after deployment.

Important: the server dataset calendar expires 9 November 2026. Separately
schedule a resource-controlled new GTFS import without overloading this
shared hosting account. Do not automatically import multi-million-row
GTFS feeds as part of this hotfix.


## Live deployment and post-deployment evidence (28 October 2026)

**The one-file router change is deployed.** The production deployment workflow
verified the original live router's checksum matched the audited v0.2.5
source, then made an atomic PHP swap after backing up the original.
Post-deployment checksum, PHP syntax and function-presence checks succeeded:
https://github.com/bengoodman654/openroad/actions/runs/40715537078

A separate read-only PHP smoke check against the current real South West
dataset proved that a known scheduled direct trip selected from the database
can be recovered by the new optimized candidate query; total duration was
approximately **80 ms** with a deliberately restrictive SQL timeout.
https://github.com/bengoodman654/openroad/actions/runs/40716414914

**Remaining route availability gap:** A representative South Bristol–Clifton
coordinate pair returned no direct candidate and no same-stop transfer
candidate despite more than 120 valid scheduled arrivals near Clifton
during the selected five-hour window. This does NOT establish there is no
public-transport journey. The legacy v1 engine cannot join two bus services
that require a walk between different stop IDs (and has not verified safe
pedestrian transfer connectivity). The v2 stop-side/pedestrian connector
work remains incomplete and intentionally unshipped.

No schema/import/GTFS jobs were run on the live JustHostMe shared host.
The app stays at **0.6.32**; the change is on its server only.
The user should re-run their actual South Bristol–Clifton journey and
report whether they receive an itinerary, a no-route outcome, or SQLSTATE
again. Exact selected endpoints may materially differ from the representative
fixed-coordinate smoke test.
