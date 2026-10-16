# Upgrade OpenRoad Transport Server v0.2.1 → v0.2.2

This upgrade preserves your database credentials, paired-device keys, server secret and existing timetable data. **Do not overwrite `/home/bengoodm/openroad-private/config.php`.**

Copy the files from the v0.2.2 upgrade package over the matching paths in your existing installation, then run:

```bash
php /home/bengoodm/openroad-private/bin/upgrade_0_2_2.php
```

The upgrade may spend a little time adding a covering index to the existing South-West timetable. Leave it to finish.

Then rebuild South West once so the server stores full BODS route shapes rather than the older sampled shapes:

```bash
php -d memory_limit=768M /home/bengoodm/openroad-private/bin/update_gtfs.php south_west
```

Keep your existing nightly South-West refresh. Add these two cron jobs as well:

```text
*/10 * * * * php -d memory_limit=768M /home/bengoodm/openroad-private/bin/process_preload_queue.php >> /home/bengoodm/openroad-private/logs/preload.log 2>&1
31 4 * * * php /home/bengoodm/openroad-private/bin/cleanup_regions.php >> /home/bengoodm/openroad-private/logs/cleanup.log 2>&1
```

The first processes one requested destination/current-area preload at a time. The second removes temporary regions unused for 60 days. South West is permanent and is never expired.

No setup rerun or phone re-pairing is required.
