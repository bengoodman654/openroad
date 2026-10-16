# ClearRoute 0.1.5

## Location reliability
- Adds Google Play services Fused Location Provider 21.4.0 as the primary enhanced location source on supported Android phones.
- Keeps Android GPS and network LocationManager providers active as a fallback.
- Requests a fresh high-accuracy fused fix when the user presses the current-location button or when a route needs an origin.
- Adds a 15-second status timeout rather than leaving the interface indefinitely on “Getting your current location…”.
- Adds `ClearRouteLocation` Logcat messages identifying successful and failed location providers.
- Adds a Settings switch named **Enhanced location on this phone**. Turning it off disables the Google Play services location source and leaves only Android GPS/network providers.
- Navigation foreground service now uses the same fused + framework fallback approach.

## Walking
- Adds a **Walk** travel mode.
- TomTom routing uses `travelMode=pedestrian` for walking.
- Traffic is requested only for driving routes.
- Walking navigation uses tighter off-route and voice-announcement distances.

## Home
- Adds a house shortcut at the right-hand end of the search bar.
- Home is configured in Settings by searching for an address/postcode and tapping a result.
- Home is stored locally in private SharedPreferences; it is not uploaded to a ClearRoute server.
- Pressing the house shortcut immediately sets Home as the destination and requests directions using the currently selected Drive/Cycle/Walk mode.
