# ClearRoute 0.3.0 — on-road reliability update

## Routing and restrictions
- Driving requests now ask TomTom to avoid carpool/HOV-only and unpaved roads as a defensive default.
- Routes request travel-mode sections. If TomTom returns alternatives that are valid for the requested mode, routes containing an unavailable/`other` travel-mode section are removed.
- A remaining route with uncertain travel-mode access is explicitly flagged in the route chooser instead of being silently presented as normal.
- Driving routes use `departAt=now`, so TomTom can apply time-dependent restrictions where its coverage contains them.

These measures reduce inappropriate routes, but they cannot make missing provider restriction/closure data appear. A bus lane or newly closed pedestrian bridge can still be absent from TomTom data.

## In-navigation detours
The navigation bar now has **Options**:
- **Reroute now** asks TomTom for a fresh route from the current position.
- **Avoid road ahead** creates a small temporary avoid rectangle around the route roughly 95 m ahead when driving (smaller for cycling/walking), then recalculates around it.
- Up to six manual avoid areas are kept for the running navigation service so automatic rerouting does not immediately choose the same blocked point again.

## Rural GPS stability
- Rejects implausible short-interval position jumps rather than drawing them.
- Very poor recent fixes are ignored when a better accepted fix is available.
- While the raw fix remains plausibly near the route, the displayed blue marker is snapped to the calculated route line. Raw GPS is still used for off-route detection.
- Display speed is smoothed to reduce one-fix spikes.

## Driving speed display
During driving navigation ClearRoute now shows:
- current GPS-derived speed in mph;
- the TomTom legal speed-limit section for the current route position in a UK-style circular sign, when TomTom supplies one.

A dash means no reliable speed limit was returned. ClearRoute does not infer or guess a missing legal limit.

## Map appearance
The build-time ClearRoute map palette is brighter while retaining the navigation hierarchy:
- stronger green parks/grass/woodland;
- warmer farmland;
- brighter blue water;
- pale yellow local roads through progressively stronger gold/yellow main roads;
- blue motorways;
- warmer residential/building areas;
- no permanent generic POI clutter.

## Screen behaviour
`FLAG_KEEP_SCREEN_ON` is now set for the ClearRoute Activity whenever it is in the foreground, not only during active navigation.

## App icon
The chosen OpenSuite Option 3 package is the intended final icon family. The exact Navigation PNG could not be copied into this source bundle because the prior File Library item was available only as a file reference, not raw bytes in this execution environment. The existing ClearRoute launcher icon therefore remains temporarily; this is an asset-only follow-up, not an app-code dependency.
