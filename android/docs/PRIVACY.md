# ClearRoute privacy model

## Data that stays on the phone
- Raw current device location fixes, except coordinates necessarily sent for route calculation and optional search bias.
- Encrypted TomTom API key.
- Home and favourites.
- User settings including alert mode and chosen TTS engine/voice.
- The currently active route in Android's temporary cache so navigation can recover from Activity/process recreation. It is deleted on normal stop/arrival and expires after 12 hours if cleanup cannot run. v0.2.0 also removes the legacy active-route file used by earlier builds.

ClearRoute v0.2.0 has no route-history or search-history database.

## Data sent externally

### OpenFreeMap
Map style/vector-tile requests necessarily disclose the requested map tiles and public IP address to that provider.

### TomTom
- Search: entered query; current coordinates only when search-location bias is enabled.
- Routing: current origin, selected destination, travel mode and routing options.
- Traffic overlay: map tile coordinates for the area displayed.

### Google Play services location (optional)
When **Enhanced location on this phone** is enabled, ClearRoute obtains device location through Google Play services' Fused Location Provider. This is not Google Maps Platform and ClearRoute uses no Google Maps API key. The setting can be disabled to use Android framework GPS/network providers instead.

### ClearRoute / JustHostMe
Nothing. v0.2.0 has no ClearRoute backend call.

## Diagnostic logging
ClearRoute does not intentionally write precise latitude/longitude values to its diagnostic logs. Provider state, errors and location accuracy may be logged during development/debugging.

## Deliberately absent
- account/login;
- advertising SDK / advertising ID request;
- analytics SDK / Firebase;
- cloud favourites sync;
- permanent route/location history.
