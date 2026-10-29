# ClearRoute 0.1.7 changes

## Navigation start fix

- Fixes a false **Could not start navigation** message that could appear after the navigation service had already started successfully.
- Cause: `startNavigation()` is invoked through Android WebView's JavaScript bridge thread, but v0.1.6 changed the Activity window's `FLAG_KEEP_SCREEN_ON` directly from that thread. On affected devices that UI operation throws after the foreground navigation service has already started.
- Window flag changes now run on Android's main UI thread.
- The same threading correction is applied when stopping navigation.
- Genuine navigation-start exceptions are now logged under `ClearRouteNavigation`.

## ClearRoute map palette

The OpenFreeMap/OSM-derived map remains deliberately uncluttered, but its navigation-relevant geography now has a clearer hierarchy:

- Parks: light green.
- Grass: light green.
- Farmland/fields: pale green.
- Woodland: slightly deeper light green.
- Rivers, canals, lakes and other water: light blue.
- Minor/service roads: very pale yellow.
- Tertiary roads: light yellow.
- Secondary roads / typical B-road hierarchy: medium-light yellow.
- Primary roads: stronger yellow.
- Trunk roads: dark yellow/gold.
- Motorways: blue with a darker blue casing.

Positron does not normally draw grass and farmland classes. ClearRoute adds those two fills directly from OpenMapTiles' existing `landcover` vector layer; this adds no POI markers and no new external data provider.
