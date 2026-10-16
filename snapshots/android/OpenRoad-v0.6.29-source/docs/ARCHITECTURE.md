# ClearRoute 0.2 architecture

## Map
- OpenStreetMap-derived vector data served by OpenFreeMap.
- MapLibre GL JS packaged inside the APK and rendered in a hardened Android WebView.
- ClearRoute adds its own navigation-first map layers from OpenMapTiles source classes and hides generic POI clutter.

## Location
- Outside active navigation: Fused Location Provider is primary when Enhanced location is enabled; Android framework GPS/network providers are fallback. Enhanced location can be disabled.
- During active navigation: the foreground `NavigationService` is the sole high-frequency location owner. It uses Fused Location primarily or framework providers as fallback.

## Search and routing
- TomTom Search for explicit UK place/address search.
- TomTom Routing REST API for car, bicycle and pedestrian routes.
- Driving uses live traffic. ClearRoute can compare the fastest live route with a no-current-traffic baseline to make traffic-driven deviations understandable.

## Navigation engine
ClearRoute keeps a small local navigation layer rather than using a full commercial Navigation SDK:
- project each GPS fix onto the relevant route segment;
- maintain monotonic route progress;
- calculate turn distance along the route;
- use TomTom instruction route offsets and announcement points where available;
- estimate remaining time from cumulative instruction travel times;
- heading-up follow camera with route-bearing fallback;
- voice / edge-flash / silent manoeuvre alerts;
- reroute after repeated sufficiently accurate off-route fixes;
- active route recovery from temporary cache;
- foreground navigation notification.

This remains intentionally auditable and dependency-light. It is not yet lane-level/map-matched navigation quality.

## State/privacy
- Preferences/Home/favourites/API key are local only.
- API key is encrypted using Android Keystore.
- Active route is cache-only, cleared on normal end and time-limited for crash/process recovery.
- No analytics, advertising, account or ClearRoute backend.

## Future data layers
Government roadworks/closure adapters, speed-limit information, cycling elevation and offline support remain separate future work and are not represented as implemented.
