# ClearRoute v0.6.0

## Map-first redesign
- Rebuilt the interface around familiar modern navigation conventions while retaining ClearRoute branding, privacy and data providers.
- Floating search bar, Home and Saved shortcuts, circular map controls, bottom place sheet and bottom route sheet.
- OpenFreeMap Bright remains the base map; useful place labels are visible by default. No sponsored markers or advertising are injected.
- New Layers sheet for live traffic, cycling infrastructure and place-label visibility.

## Destination and route experience
- Selecting/searching a place now opens a place sheet with Directions and Save actions.
- Saved places are kept locally on the phone, can be reopened from the home screen or Settings, and can be removed.
- Route preview now uses a blue selected route with grey alternatives and white casings for legibility.
- Alternative routes can be selected from route cards or by tapping their line on the map.
- Route cards retain travel time, distance, traffic delay, important roads and restriction warnings.
- Added a route Steps sheet showing turn-by-turn instructions before navigation.
- Travel-mode controls now live in the route sheet rather than permanently covering the map.

## Navigation experience
- Large blue manoeuvre banner with turn symbol, distance and instruction.
- Bottom navigation sheet now shows estimated arrival time, remaining time and remaining distance.
- Existing live speed and speed-limit displays are retained.
- Added quick navigation-alert control cycling Voice -> Edge flash -> Silent.
- Added Route overview control. Panning/zooming still suspends follow mode and the blue location button recentres.
- 2D/3D control and in-route Reroute/Avoid road ahead options are retained.

## Privacy
- No ClearRoute account, advertising, sponsored results, analytics, location history or permanent route history.
- Home and saved places are local-only.
- The bundled TomTom key remains for this personal sideloaded build; do not publish this source/APK publicly.
- Useful labelled places on the Bright map can now be tapped to open the ClearRoute place sheet; long-press remains available for an exact dropped pin.
- Driving Route options now include Avoid motorways, Avoid toll roads and Avoid ferries, persisted locally and honoured by reroutes.
