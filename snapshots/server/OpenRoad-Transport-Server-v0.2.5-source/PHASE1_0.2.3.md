# OpenRoad Transport Server v0.2.3 — Phase 1 maintenance update

## What changed

- Early, explicit error for regional-bus queries crossing unsupported regions or requesting Bristol-to-London intercity rail; no expensive futile SQL exploration.
- Session-scoped SELECT statement timeout attempted for MariaDB (`max_statement_time`) and MySQL (`max_execution_time`); unsupported server variables are ignored without breaking routing. Actual query timeouts depend on the hosting SQL engine and permissions.
- Application-side 4.5-second fast-phase and 6.5-second full-phase cooperative routing budgets, including checks between queries. PHP cannot forcibly cancel an already-running SQL request: the database limit is important.
- Per-stage cumulative elapsed timings (`clearRouteStagesMs`), total elapsed (`clearRouteTimingMs`) and cache hit/miss status included in successful responses.
- Private aggregate JSON-lines diagnostic log: `private/logs/journey-timings.jsonl`. Logs durations, search phase, cache hit, result count and outcome, but not coordinates, destinations, API keys or device identifiers.
- Failure to cache a valid journey no longer invalidates that journey.

## Upgrade without deleting your configuration

1. Back up the current `openroad-private` directory and existing `public/api/v1` files.
2. Extract **OpenRoad-Transport-Server-v0.2.3-upgrade.zip** locally.
3. Upload the three files in `private/lib/` into `/home/bengoodm/openroad-private/lib/` (replacing same-named files), and the two files in `public/api/v1/` into your existing OpenRoad subdomain's `api/v1/` directory.
4. The upgrade ZIP deliberately does NOT contain `private/config.php`, the private cache, the database schema, pairing keys or database credentials. Do not rerun `setup.php`, `upgrade_0_2_2.php`, or `update_gtfs.php` for this change. No schema migration is needed.
5. Check `php -l` against the changed PHP files before testing.
6. After a test journey, check `private/logs/journey-timings.jsonl` and (on successful routes) the `clearRouteStagesMs` response field.
7. Restore the five backed-up files if a hosting-specific SQL problem occurs.

**Scope:** This improves bounded failure and troubleshooting, but does not itself add rail routing or guarantee a valid complete journey within 20 seconds. Long-distance rail planning remains Phase 2. Test on a staging installation first if possible.
