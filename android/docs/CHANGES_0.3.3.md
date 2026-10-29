# ClearRoute v0.3.3

- Removed the blocking startup overlay introduced in v0.3.2. A slow or failed basemap can no longer cover the entire app.
- Kept the bundled personal TomTom API key and corrected adaptive icon.
- Added WebView page-load diagnostics without blocking the interface.
- Added a non-blocking OpenFreeMap Bright fallback if the packaged ClearRoute style does not initialise promptly.
- Native location/search/settings are released after a timeout even if map networking is unavailable.
- Makes any relative glyph, sprite or source URLs in the packaged OpenFreeMap-derived style absolute at build time.
