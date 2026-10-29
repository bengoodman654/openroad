# ClearRoute 0.1.2

This maintenance build fixes the first physical-device fault found on a Samsung Galaxy Note 8.

## Fixed

- The TomTom API-key setup dialog is now shown before map initialisation, so a map-rendering failure cannot suppress setup.
- MapLibre GL JS and CSS are downloaded at **build time** and packaged inside the APK. The phone no longer depends on `unpkg.com` at runtime just to start the map.
- Local web assets are loaded through Android `WebViewAssetLoader` using the secure `https://appassets.androidplatform.net` origin instead of `file://`.
- Hardware acceleration is explicitly enabled for the application's WebGL map.
- Search failures now replace `Searching…` with the actual error, including a missing TomTom API key.
- Map startup now reports a visible error if the renderer or online map style fails to load.

## Still online by design

The packaged renderer does not package UK map data. OpenFreeMap vector tiles/style resources are still requested over HTTPS, and TomTom search/routing/traffic calls remain online services.
