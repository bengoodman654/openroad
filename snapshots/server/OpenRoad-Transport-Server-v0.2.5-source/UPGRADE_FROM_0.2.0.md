# Upgrade OpenRoad Transport Server v0.2.0 → v0.2.2

This upgrade does **not** change your database, pairing keys, database password, private server secret, or cron job.

Back up the existing three destination files first if you wish, then copy/overwrite only:

1. `private/lib/router.php` → `/home/YOURUSERNAME/openroad-private/lib/router.php`
2. `public/api/v1/journeys.php` → `/home/YOURUSERNAME/public_html/openroad-api/api/v1/journeys.php`
3. `public/api/v1/service.php` → `/home/YOURUSERNAME/public_html/openroad-api/api/v1/service.php` (new file)
4. `public/api/v1/status.php` → `/home/YOURUSERNAME/public_html/openroad-api/api/v1/status.php`

Do **not** overwrite `/home/YOURUSERNAME/openroad-private/config.php`.
Do **not** rerun setup or pair the phone again.
Do **not** clear the OpenRoad database.

After copying the files, in cPanel Terminal run:

```bash
php -l /home/YOURUSERNAME/openroad-private/lib/router.php
php -l /home/YOURUSERNAME/public_html/openroad-api/api/v1/journeys.php
php -l /home/YOURUSERNAME/public_html/openroad-api/api/v1/service.php
```

All should report `No syntax errors detected`.

The existing nightly GTFS updater and indexed dataset can be reused immediately. The next scheduled update will continue normally.
