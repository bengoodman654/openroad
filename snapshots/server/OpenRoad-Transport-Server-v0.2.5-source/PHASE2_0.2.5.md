# OpenRoad Transport Server v0.2.5 — BODS on-demand gateway

Adds `POST /api/v1/bods.php`, using the *existing* signed phone authentication.
The server fetches BODS vehicle monitoring XML using the `bods_api_key` in the existing
`/home/bengoodm/openroad-private/provider-secrets.php`. The key is **never returned to Android**.

## Shared hosting limits

- Strictly manual live-bus button only: **no new cron, daemon, background importer or live polling**.
- Maximum **eight upstream BODS calls per UTC hour**, shared by all paired devices; failures consume quota.
- **One concurrent upstream request**, max **2.5 seconds** network timeout, **256 KiB** response limit.
- Geographical bounding box ~8 km wide and cache tile ~1 km; cache for **60 seconds**.
- Failure cache **45 seconds** to prevent immediate retries.
- Maximum **32 location/line cache entries**; the cache can grow to at most about 11 MB worst case.
- Fixed BODS HTTPS host; no redirects; no client-provided URLs or arbitrary queries.
- Existing GTFS ingest, bus journeys, Rail Data, WordPress, email and database schemas untouched.
- If an unexpected upstream XML response is too large or times out, return a safe 503 instead of escalating workload.
- The server proxies bounded XML; Android's existing SIRI-VM parser interprets it. No additional PHP XML extensions required.

## Server configuration

SSH to JustHostMe and edit the existing private `provider-secrets.php` (outside public_html),
**preserving the working `raildata_consumer_key`**. Add a separate entry:

```php
'bods_api_key' => 'YOUR_EXISTING_BODS_KEY',
```

Do not paste keys into chat, public GitHub, cPanel public_html or Android source.
Run `chmod 600 /home/bengoodm/openroad-private/provider-secrets.php` and `php -l`.

## Deployment and testing

- Upload both source and `OpenRoad-Transport-Server-v0.2.5-upgrade.zip` to GitHub.
- GitHub `TEST` checks SSH and the existing PHP files; it **does not** contact BODS or validate the new key.
- Run `DEPLOY` only after setting the key. The GitHub workflow backs up all existing allowlisted files and supports removal of two new files on rollback.
- Install Android v0.6.29 **over the existing app**, preserving device pairing.
- Search a Bristol bus number, then tap **Live buses** *once* to test.
- If you have no BODS subscription or the key is missing, live vehicle display gives a controlled error; timetable routing remains unaffected.

TfL (two subscription keys), TransportAPI (app ID and key), and TomTom are identified from earlier Open Road chats but not yet moved; they require separate scoped proxy/SDK assessment to avoid harming the working app or shared hosting.
