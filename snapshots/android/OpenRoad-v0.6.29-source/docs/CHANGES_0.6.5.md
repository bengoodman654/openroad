# OpenRoad v0.6.5

## Rename and personal API setup
- Renamed the user-facing app from **ClearRoute** to **OpenRoad**.
- Kept the Android application ID (`uk.co.bengoodman.clearroute`) and existing local preference/cache identifiers unchanged so this build installs as an update and retains local settings/starred places.
- The personal TomTom API key is bundled at build time and copied into Android Keystore on first launch. Traffic, driving routes and TomTom search therefore require no first-run key entry.
- Updated service/client identifiers to OpenRoad 0.6.5 while retaining the internal JavaScript/native bridge name for backwards-safe source continuity.

## Interface
- Replaced thin text × / ← controls with larger high-contrast SVG close/back buttons and 42 dp touch targets.
- Redesigned along-route map results: the exact location is now a dot, with the POI symbol and added journey time in an offset callout connected by a leader line.
- Added collision-aware callout placement. OpenRoad tries multiple positions and progressively larger offsets, recalculating during map movement/zoom/rotation to keep nearby added-time labels legible.

## Traffic
- Retains the TomTom Orbis v2 live flow and incident raster overlays already present in v0.6.4. Traffic remains independent of travel mode and visible whenever the Traffic layer is enabled.
