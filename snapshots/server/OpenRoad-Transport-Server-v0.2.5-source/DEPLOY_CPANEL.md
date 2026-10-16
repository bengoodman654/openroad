# Safe cPanel deployment — OpenRoad Transport Server v0.2.2

Use a dedicated subdomain/document root and keep the private directory outside `public_html`:

```text
/home/bengoodm/openroad-private/
/home/bengoodm/public_html/openroad-api/
```

Do not modify the document roots, `.htaccess` files or databases of existing websites.

For a fresh install, copy `private/` to `/home/bengoodm/openroad-private/` and the contents of `public/` to `/home/bengoodm/public_html/openroad-api/`. Create a dedicated MySQL database/user, edit only the database values in `openroad-private/config.php`, then run:

```bash
php /home/bengoodm/openroad-private/bin/setup.php
php -d memory_limit=768M /home/bengoodm/openroad-private/bin/update_gtfs.php south_west
```

Pair OpenRoad using the one-time code from `setup.php`.

Recommended cron jobs:

```text
17 3 * * * php -d memory_limit=768M /home/bengoodm/openroad-private/bin/update_gtfs.php south_west >> /home/bengoodm/openroad-private/logs/update.log 2>&1
*/10 * * * * php -d memory_limit=768M /home/bengoodm/openroad-private/bin/process_preload_queue.php >> /home/bengoodm/openroad-private/logs/preload.log 2>&1
31 4 * * * php /home/bengoodm/openroad-private/bin/cleanup_regions.php >> /home/bengoodm/openroad-private/logs/cleanup.log 2>&1
```

South West is permanent. Other supported English BODS regions are downloaded only after a destination/manual/daily-area request and expire after 60 days of non-use. London uses TfL directly and is not mirrored.
