# OpenRoad v0.6.22

## Public-transport map stability

- Public-transport stop dots are now rendered as MapLibre GeoJSON circle layers rather than HTML markers laid over the map. The dots and route lines therefore use the same geographic projection and remain locked to their coordinates through zooming and panning.
- Stop dots retain a larger invisible tap target, so they remain easy to open without making the visible dots oversized.
- Live timetable/geometry enrichment no longer tears down and redraws the public-transport overlay in the middle of a pan or pinch-zoom. If genuinely new geometry arrives during a gesture, the map waits until the gesture has ended and applies it without changing the camera.
- Live updates preserve the currently selected journey by its stable route ID whenever that journey still exists.

## Simpler public-transport results

- Removed the user-facing **Maximum walking** setting and the post-result walking-limit filter.
- The on-device BODS fallback now searches a generous internal stop catchment instead of using a user walking cap to reject journeys. Walking time still contributes to route timing and ranking.
- Public transport now presents at most the best **three** journeys for the selected priority: **Quickest**, **Balanced**, or **Fewest changes**.
- Removed **Load 3 more** from the public-transport results.
- Changing the ranking priority now runs a fresh public-transport search so the provider/planner can return the best three for that criterion rather than merely rearranging the previous three.
- Changing public-transport mode, walking-speed, connection-margin or accessibility settings also recalculates the active public-transport search.
- Old saved `maxWalk` preferences are ignored automatically when upgrading.

## Compatibility

- Android source version: **0.6.22** (`versionCode 82`).
- Compatible with OpenRoad Transport Server **v0.2.2**. The app sends the existing unlimited-walking sentinel (`maxWalk: 999`) for compatibility; no server deployment is required for this app update.
