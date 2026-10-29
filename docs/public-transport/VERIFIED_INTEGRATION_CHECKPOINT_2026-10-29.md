# OpenRoad unified release — verified engineering checkpoint, 29 October 2026

## Working production baseline
Android 0.6.32 continues to work with Cloudflare proxying; the user confirmed South Bristol–Clifton public-transport navigation still works. Live server v0.2.9 retains SQL-index/fairness corrections. Its South West calendar was extended to 13 December 2026 through the private calendar-only maintenance CLI. Do not replace current source or routing with the older v0.6.31/v0.2.5 pilot ZIPs.

## Integration actually completed on this branch
1. Signed PHP v2 issue/route/cancel/status and device ownership libraries were ported from pt-v2-planner-hardening to integration/ptv2.
2. A staged server is generated from the exact version-controlled v0.2.5 original, applies BOTH production router hotfixes v0.2.8 and v0.2.9, then inserts the optional callback and signed v2 libraries into the *isolated* ZIP. The original v1 public endpoint remains untouched.
3. The staged server PHP regression, authentication ownership, cancellation-before-start, late cancellation, HMAC tamper, snapshot pinning and two-independent-worker process tests pass. CI run: https://github.com/bengoodman654/openroad/actions/runs/40862736632.
4. A staged Android candidate starts from the exact released v0.6.32 source, changes only OpenRoadServerClient.java and TransitClient.java and compiles with Gradle. The original installed Android navigation UI and normal v1 transport path remain untouched. v2 research mode is gated by BuildConfig.DEBUG and a non-exposed ptV2Research setting; no production route has been silently replaced. CI run: https://github.com/bengoodman654/openroad/actions/runs/40862736509.
5. The 105-case production release manifest and fail-closed evidence gate were copied from the research branch. The gate passes its own unit tests and still reports 0 accepted real-world production cases: https://github.com/bengoodman654/openroad/actions/runs/40863078308.
6. Off-host fresh regional GTFS indexing jobs independently succeeded for South West and West Midlands, including SQLite quick_check, regional probes and compact-index parity. These do not imply the live server data has been refreshed: https://github.com/bengoodman654/openroad/actions/runs/40861435321.

## Release blockers — not solved merely by green source checks
- The signed v2 endpoints have NOT been installed on JustHostMe; current live app and live PHP v1 work. A proper production v2 request needs network integration plus a safely pinned dataset and exact authentication/SQL load checks.
- Android v2 wiring compiles but remains deliberately inert; it currently reports research outcomes as non-navigable. This is not a finished v2 transport planner.
- No field-verified directional boarding-kerb-to-footway or between-stop walking connector is installed. Stop-code/OSM proximity does not provide legal/safe pedestrian geometry.
- Real rail+bus orchestration, current rail entitlements, realtime freshness, via-stop semantics, actual Coventry source coverage and the field acceptance matrix are not yet proven end-to-end.
- Current calendar extension is based on the older cached feed; an off-host indexed fresh dataset needs a carefully versioned production rollout. The broken 03:17 bulk cron needs controlled retirement/rollback.
- No new signed Android release has been published from this branch. Never claim complete app or 105/105 tests.

## How to continue
Next actual engineering work is to wire the fresh indexed feeds into a source-pinned, bounded server planner on this branch, with a tested real walking-access source and honest unavailable/provisional states. Verify real Bristol and Coventry field journeys, then integrate rail and live data and activate the API in a controlled deployment. Preserve the same Android package/signing and normal updater for the eventual release.

No additional action is currently required from the user to keep current OpenRoad functioning.
