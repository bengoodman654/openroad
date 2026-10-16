# OpenRoad 0.6.12

## Routing flow and defaults
- Driving is now the deliberate default whenever the app starts and whenever a new destination is chosen.
- Public-transport data is not prepared or requested until the user explicitly selects Public transport.
- The public-transport planner panel now visually drops down from the main **Where to?** search box.
- The minimised Directions/Journey/Bus sheets sit above the Android safe-area and expose a larger, labelled restore tab.

## Faster public-transport results
- DfT/BODS timetable routing is returned before live-data enrichment. Live BODS vehicle positions and Darwin predictions update the displayed journeys afterwards instead of blocking the first result.
- Published BODS shape geometry is also staged: timetable results initially use stop-to-stop geometry, then the precise route shape is loaded locally and updates the map.
- Regional GTFS stop, route and active-trip metadata is cached in memory for the current timetable file/date, reducing repeated parsing on subsequent searches.
- Selecting Public transport warms the relevant regional timetable cache; no public-transport preparation occurs before that selection.
- Concurrent regional timetable preparation and routing share the same download/cache locks to avoid duplicate downloads/parsing.

## Behaviour
- Public-transport results show a short **Finding public transport…** state explaining that timetable routes arrive before live positions.
- Live updates preserve the currently selected result rather than resetting the journey list.
