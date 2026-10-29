# OpenRoad v0.6.27 — Phase 2 rail integration foundation

- Adds a live **Rail Data Marketplace departure-board diagnostic** under Settings → Services & API keys → National Rail. Enter a three-letter CRS code (defaults to BRI for Bristol Temple Meads), then press **Check departures**.
- Tests the existing RDM consumer key without modifying routes, timetable data or server pairing. Requests use the official RDM LDB endpoint and `x-apikey` header over HTTPS; key is read from encrypted Android storage and never passed to the HTML UI or log.
- Displays live scheduled/estimated departures, destination and platform, or a specific authentication failure message. This is **not** full intercity journey planning: RDM's live departure board is a distinct product from National Rail's point-to-point routing engine.
- Compatible with v0.6.26 application signing and in-place updates. The private transport server remains on v0.2.3; this Android-only upgrade cannot change its database.
- All provider credentials remain empty in the distributable source. Manually configured Android credentials survive an over-install with matching signature. Personal GitHub build secrets may seed an APK, but secrets in an APK are extractable; do not distribute key-bearing builds.

## Test checklist
1. Update **over** v0.6.26 (do not uninstall), check server still says ready and local Bristol public-transport routing still works.
2. Open Settings → Services & API keys → National Rail, confirm whether Rail Data Marketplace is configured.
3. If configured, press **Check departures** for `BRI` or another valid CRS. Confirm actual departures show, or the provider error is explained.
4. If not configured, enter the consumer key once via the encrypted settings field and repeat. The departure test does not require BODS, TfL or TransportAPI keys.
5. Check Android updater path on a fresh v0.6.26 install and confirm Android keeps the same package and settings.
