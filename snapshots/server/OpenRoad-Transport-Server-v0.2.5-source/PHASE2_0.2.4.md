# OpenRoad Transport Server v0.2.4 — low-impact rail gateway

* Adds `POST /api/v1/rail.php`, accepting `{ "station": "BRI" }` with the **same signed Android device authentication** as the bus router.
* No extra database schema, no timetable import, no cron or daemons, **no changes to existing bus routes**.
* Credentials reside only in `/home/bengoodm/openroad-private/provider-secrets.php` (manually provisioned on hosting); the example file is deliberately not deployed.
* Upstream rail requests: global **12 calls/hour** across paired devices, at most **one outstanding upstream request**, **2.5-second** network timeout, **64 KiB** response limit, **8** departures max, **120-second** on-disk cache per CRS, **45-second** failure caching. Return quick 503/429 on contention or budget exhaustion.
* Cache is in `/home/bengoodm/openroad-private/cache/rail-v1`, not public_html. Budget file is one small JSON file. No polling. Rail data fetched only on an explicit departure-board request.
* Caches include only public station and service board information; no user location or API keys.
* This is the FIRST, read-only provider migration, not a national journey planner. TfL, BODS live vehicles and TransportAPI remain in Android v0.6.27 and need separate migration.
* Existing GTFS cron jobs may be heavier than this gateway. Audit them before adding new feeds/regions; **do not increase** their memory or frequency.

## Credential provisioning (do not paste secret in chat)

SSH into JustHostMe and use `nano /home/bengoodm/openroad-private/provider-secrets.php`; paste the structure from `private/provider-secrets.example.php` with your real RDM **consumer** key. Run `chmod 600 /home/bengoodm/openroad-private/provider-secrets.php`. Do not put this private file inside public_html or GitHub.

## Safe upgrade

Run `TEST` first. `DEPLOY` backs up four existing PHP files and atomically adds two new endpoints (`private/lib/rail_gateway.php`, `public/api/v1/rail.php`). Rollback removes new files if the deployment fails. No provider request is made by the deployment itself.
