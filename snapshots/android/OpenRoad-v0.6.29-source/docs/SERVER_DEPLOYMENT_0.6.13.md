# Deploying OpenRoad Transport Server safely in cPanel

This package is designed to live in a **new, isolated subdomain document root**. It does not need to alter WordPress, `.htaccess`, PHP files, databases, or DNS records belonging to any existing website.

## Recommended layout

Create the subdomain:

`openroad.bengoodman.co.uk`

with a separate document root such as:

`public_html/openroad-api`

The entire contents of this server ZIP go inside that new `openroad-api` folder. Do **not** select an option that shares the document root with `bengoodman.co.uk`.

## Database

Create a new database called `openroad` and a new database user called `openroad` with a generated strong password. cPanel will normally prefix both names with your cPanel username. Grant this user **ALL PRIVILEGES on the OpenRoad database only**.

Then edit `private/config.php` and replace only:

- `CPANELUSER_openroad` under `db_name`
- `CPANELUSER_openroad` under `db_user`
- `CHANGE_ME_TO_THE_DATABASE_PASSWORD`

Leave `db_host` as `localhost` unless your host explicitly tells you otherwise.

## First update

Run `private/bin/update_gtfs.php` once from cPanel Terminal if available, or create the cron job below and temporarily set it to run in a few minutes. The first import is the slow one because it downloads and indexes the regional GTFS timetable.

## Daily cron

Use cPanel **Cron Jobs** to run the updater once per day, preferably in the early morning. Replace `CPANELUSER` with the home-directory username shown by cPanel File Manager:

`/usr/local/bin/php -d memory_limit=512M /home/CPANELUSER/public_html/openroad-api/private/bin/update_gtfs.php >> /home/CPANELUSER/public_html/openroad-api/private/logs/update.log 2>&1`

A suggested schedule is **03:17 every day**. Do not run it every few minutes; the DfT schedule feed is updated daily and overlapping imports would waste server resources.

If `/usr/local/bin/php` is not the PHP CLI path on your host, cPanel's Terminal or hosting support can tell you the correct path. Common alternatives include `/usr/bin/php`.

## Checks

1. Open `https://openroad.bengoodman.co.uk/` in a browser. Before the first import it should report that the database is not yet ready; after the import it should show `datasetReady: true`.
2. Do not browse to anything under `/private/`; it should return 403/404.
3. Make sure the subdomain has a valid HTTPS certificate before using it from OpenRoad.
4. OpenRoad v0.6.13 has the matching API URL and private token preconfigured. If the server is unavailable, OpenRoad falls back to its on-device BODS planner rather than breaking Directions.
