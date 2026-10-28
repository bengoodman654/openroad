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
