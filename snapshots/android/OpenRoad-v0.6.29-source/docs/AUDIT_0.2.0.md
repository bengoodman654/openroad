# ClearRoute 0.2.0 — from-scratch audit

This audit was triggered after a real-device test in which turn text updated but the map did not provide usable visual navigation.

## High-severity fixes

1. **Navigation bearing was dropped between the foreground service and WebView.**
   `NavigationService` broadcast `hasBearing`, but `MainActivity` did not forward it to JavaScript. The navigation camera therefore could receive a heading value while being told that no heading existed. v0.2.0 forwards both `bearing` and `hasBearing` and uses route bearing as a low-speed fallback.

2. **North (0°) was treated as a false value in JavaScript.**
   Navigation camera code previously used truthiness for bearings. v0.2.0 uses numeric validity, so a legitimate 0° bearing works.

3. **Off-route detection measured distance to route vertices rather than route segments.**
   This can falsely report a vehicle as off-route on long or curved polyline segments. v0.2.0 projects each fix onto the route line and measures perpendicular distance to the nearest relevant segment.

4. **Turn distance used straight-line distance.**
   v0.2.0 measures distance to the next instruction along the route and uses TomTom route offsets/announcement points when available.

5. **Two high-frequency location pipelines could run during navigation.**
   The foreground Activity and navigation Service could both request location updates. v0.2.0 makes the Service the sole high-frequency location owner during active navigation. Within the Service, Fused Location is primary and framework GPS/network providers are fallback rather than simultaneous competitors.

6. **Stale asynchronous route responses could become the route actually started.**
   JavaScript ignored stale responses visually, but native `lastRouteResponse` could still be overwritten by an older request. v0.2.0 guards the native route response with the request ID as well.

## State/lifecycle fixes

- Active navigation is stored in Android's cache directory rather than permanent app files and expires automatically after 12 hours if normal cleanup cannot run. v0.2.0 also deletes the legacy permanent active-route file left by older test builds.
- Normal stop/arrival clears the cached active route immediately.
- Stopping from the notification now broadcasts a stopped state to the foreground UI.
- Automatic arrival also synchronises the UI.
- Returning to the Activity after a background reroute reloads the current cached route.
- Screen-on flags are changed on Android's UI thread only.
- Notification permission is requested when navigation starts rather than on first launch.
- Search bias, traffic visibility and selected travel mode are now persistent settings.

## Navigation UI fixes

- Starting navigation switches to a dedicated guidance view: search, mode and ordinary map controls are hidden.
- A large manoeuvre symbol is shown with the text instruction.
- Only the selected route is drawn during active guidance.
- The camera follows the current fix heading-up and uses route direction if GPS bearing is not yet trustworthy.
- The user-position pointer remains aligned to direction of travel.
- The ambiguous MapLibre compass control is removed; browsing is north-up and active navigation is heading-up.

## Routing/guidance reliability changes

- Progress is projected onto the route line and prevented from jumping backwards because of ordinary GPS jitter.
- Route crossings use a window around the previously matched segment before considering the entire route.
- Poor-accuracy fixes do not trigger rerouting.
- Rerouting requires four consecutive off-route fixes and has a cooldown.
- Remaining time is derived from TomTom's cumulative instruction travel times when available rather than scaling total ETA only by distance.
- Voice/edge alerts use TomTom early/main announcement positions when available, with local distance fallbacks.
- Cycle and walking searches now request one alternative rather than two to reduce unhelpful route-choice clutter.

## Map/usability clean-up

- Dedicated ClearRoute layers are based on OpenMapTiles source classes, not fragile Positron layer names.
- Motorway/trunk/primary/secondary/tertiary/minor road hierarchy is retained.
- Water and landcover palette is retained.
- Cycleways receive a restrained green dashed overlay **only in Cycle mode**.
- Current-location button requests a fresh fix even when a cached fix is already displayed.
- Search/route request IDs prevent late callbacks from replacing newer user actions.
- External web links cannot replace the trusted local WebView page while the Android JavaScript bridge is attached; they are opened outside ClearRoute.
- TomTom HTTP error bodies are no longer dumped into the UI; common key/quota/service errors get short user-facing messages.

## Privacy clean-up

- Precise latitude/longitude values were removed from ClearRoute diagnostic logging.
- Active route recovery data moved from permanent internal files to temporary cache.
- No route/search history database was added.

## Deliberately not claimed as fixed/tested

- This environment has no Android SDK/device, so v0.2.0 has not been APK-compiled or physically driven here.
- Lane guidance, speed-limit display, government roadworks feeds, offline routing and cycling elevation remain future work.
- Map matching is still ClearRoute's lightweight local projection logic, not a commercial navigation SDK's full map-matching engine.
