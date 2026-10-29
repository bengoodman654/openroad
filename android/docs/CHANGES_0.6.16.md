# OpenRoad 0.6.17

- The integrated Where to?/route dropdown now closes whenever the user taps outside the top route box, including the map.
- Minimized route, journey-detail and bus-timetable sheets float higher above the Android navigation area; the entire minimized tab is tappable to restore it.
- Public-transport walking legs are now asynchronously refined over OpenRoad's existing OSM/Valhalla pedestrian router, so the selected route follows real streets, footways and crossings instead of straight lines. Timetable results still appear first; walking geometry is enrichment only.
- Saved-place naming is explicit: starring a place opens the naming sheet, starred destinations expose a Rename action, and the Starred places list now has a clearly labelled Rename control instead of a small pencil glyph.
- Version/user-agent strings updated to 0.6.17.
