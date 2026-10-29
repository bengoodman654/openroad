# ClearRoute v0.4.0

## Walking/cycling Bristol safety corrections

ClearRoute still uses TomTom for walking and cycling routes, but two local routing gaps seen in real-world Bristol testing are now guarded by small built-in avoidance areas:

- **Vauxhall Bridge, Bristol** — blocked for Walk/Cycle while the current long-term repair closure is in force. The conservative built-in expiry is 1 June 2027 so a stale commercial route cannot send the user onto the closed bridge before the planned live-government-closure backend exists.
- **Cumberland Basin flyover complex** — blocked for Walk/Cycle as a personal safety preference, leaving the nearby Ashton Avenue Bridge available as the preferred pedestrian/cycle crossing.

These exclusions are deliberately local: they have no effect unless a route actually intersects the small Bristol rectangles. They also merge with ClearRoute's existing in-journey **Avoid road ahead** areas.

TomTom requests now include `departAt=now` for all travel modes so time-dependent access data can be considered where TomTom has it. Cycle requests also avoid unpaved roads where a practical alternative is available.

This is an interim safety layer, not a replacement for the planned UK local-authority/government closure feed integration.

## Map behaviour

- The OpenFreeMap **Bright** style is now ClearRoute's normal map. The abandoned custom-colour build-time style has been removed from the build pipeline.
- Generic POI/amenity/shop/tourism layers remain suppressed.
- Cycle mode still adds a restrained cycleway overlay where the Bright style exposes the OpenMapTiles `transportation` layer.

## Navigation camera usability

- Added an explicit **3D / 2D** view switch. Navigation starts in the angled 3D view; 2D is straight down.
- The same view switch is available while browsing the map.
- Dragging or pinch-zooming the map during navigation now suspends automatic camera follow instead of snapping back on the next GPS update.
- Added a persistent **Recentre** button during navigation. Tapping it resumes camera follow immediately.
- Automatic route/location/instruction updates continue while the camera is detached.

## Build simplification

The Gradle map task now packages only MapLibre GL JS/CSS. It no longer downloads, rewrites or validates a custom Positron style, reducing build-time fragility.
