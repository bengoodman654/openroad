# Private transport server deployment for OpenRoad 0.6.14

Use **OpenRoad Transport Server v0.2.0**. Do not deploy the older v0.1.0 package.

The v0.2.0 package separates files into:

- `public/` — the tiny web-facing API only. This goes in the new subdomain document root.
- `private/` — database credentials, GTFS updater, server signing/rate-limit state and logs. This must sit outside `public_html`.

Recommended locations:

- public: `/home/CPANELUSER/public_html/openroad-api/`
- private: `/home/CPANELUSER/openroad-private/`

After creating a dedicated database/user and editing `openroad-private/config.php`, run:

```bash
php /home/CPANELUSER/openroad-private/bin/setup.php
```

The setup command creates the tables, creates a private server secret and prints a one-time pairing code. Enter that code in **OpenRoad > Settings > Routing & services > OpenRoad private transport server** within 30 minutes.

Then prepare the timetable once:

```bash
php -d memory_limit=512M /home/CPANELUSER/openroad-private/bin/update_gtfs.php
```

Add the same updater as a daily cPanel cron job. The phone never needs the database password and no reusable API token is embedded in the APK.

For a replacement/new phone, run:

```bash
php /home/CPANELUSER/openroad-private/bin/reset_pairing.php
```

To inspect/revoke paired devices:

```bash
php /home/CPANELUSER/openroad-private/bin/list_devices.php
php /home/CPANELUSER/openroad-private/bin/revoke_device.php DEVICE_ID
```
