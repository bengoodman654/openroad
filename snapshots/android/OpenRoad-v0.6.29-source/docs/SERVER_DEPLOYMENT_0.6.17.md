# OpenRoad 0.6.17 server requirement

OpenRoad 0.6.17 is designed to pair with **OpenRoad Transport Server v0.2.1**.

Existing v0.2.0 installations do not need a new database, a new pairing code, or another GTFS import. Apply the small v0.2.1 upgrade package and overwrite only the listed router/API files. Your `openroad-private/config.php`, database credentials, device public key, server secret and cron job remain unchanged.

See `UPGRADE_FROM_0.2.0.md` inside the v0.2.1 server package.
