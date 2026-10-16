# ClearRoute 0.1.4

- Makes Android location delivery robust when GPS fixes arrive before the map/WebView is ready.
- Queues and renders the latest location after the map loads.
- Improves the current-location button with explicit waiting/disabled/permission feedback.
- Opens Android Location settings when the user taps Locate while phone location services are disabled.
- Selects a search result as a destination first, instead of silently attempting a route.
- Adds a visible Directions action for the selected destination.
- If Directions is tapped before a GPS fix exists, ClearRoute obtains the location and then continues route calculation automatically.
- Renames Start to Start navigation.
