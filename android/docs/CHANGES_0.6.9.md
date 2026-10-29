# OpenRoad 0.6.9

## Routing reliability
- TransportAPI journey requests now use the current documented SilverRail journey-planner engine and no longer send the previous comma-separated multi-mode query that could cause HTTP 400 responses.
- User transport-mode preferences remain enforced locally when OpenRoad ranks and displays returned journeys.
- Provider HTTP errors now include a short, sanitised upstream error message when available, so any remaining service-side configuration issue is diagnosable without exposing credentials.

## Starred places
- Map favourites are now plain gold stars with no surrounding box or label.
- Star markers scale continuously with map zoom and collapse to small gold dots when zoomed out.
- New favourites ask for a name before saving.
- Existing favourites can be renamed from the Starred places list.

## Dropped pins
- Replaced the CSS-rotated destination pin with a fixed SVG whose geographic anchor is the exact tip, preventing apparent drift as the map zoom changes.

## Controls
- The Directions button no longer destroys its icon when changing to “Calculating…”.
- Directions now uses the same outlined circular-icon treatment as the other destination actions.

- Version bumped to 0.6.9 / versionCode 69.
