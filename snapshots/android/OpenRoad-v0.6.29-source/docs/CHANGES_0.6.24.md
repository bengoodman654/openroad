# OpenRoad v0.6.24

## Route-point editing

- The route-point list is now one ordered sequence: start, intermediate stops and destination.
- Every route point has the same drag affordance, including **My location** and the final destination.
- Reordering changes the route semantics: the first item becomes the origin and the last becomes the destination.
- A dropped destination is labelled **Pin** with its latitude/longitude shown as the small secondary line. Named destinations use their place name without a redundant address line in this compact list.

## Bus routes and stops

- Bus service route stops are now rendered as MapLibre GeoJSON circle layers, using the same geographic transform as the route line. This prevents HTML-marker drift while zooming.
- An invisible larger MapLibre hit layer keeps stop dots easy to tap without changing their visible size.
- Tapping a bus-route stop opens OpenRoad's stop-service sheet, which lists services/departures known for that stop.
- Stop rows in the bus-service view now open the same stop-service sheet as map dots.

## Panels and controls

- The Places chooser is a fixed-height flex sheet: the category list scrolls independently and **Apply** remains fixed at the bottom.
- The route-sheet minimise handle has more vertical separation from Drive/Cycle/Walk/Transit controls.
- Driving **Route options** now use the same settings-panel rows and switches as the rest of OpenRoad rather than a separate-looking control group.

## Rail Data Marketplace

- National Rail live departure enrichment now supports the current Rail Data Marketplace **Live Departure Board** JSON API.
- Authentication uses the Rail Data Marketplace **Consumer key** in the `x-apikey` request header.
- Settings now expose a single Rail Data API-key field instead of the legacy Darwin username/password pair.
- `local.properties.example` uses `openroad.railDataApiKey=` for optional local bundling.

## Build

- Android source version: **0.6.24** (`versionCode 84`).
