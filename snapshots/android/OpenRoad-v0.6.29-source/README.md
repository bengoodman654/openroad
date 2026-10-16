# OpenRoad

**Current test build: 0.6.27**

OpenRoad is a private personal UK navigation app with a familiar modern map-first interface: search, inspect places, compare routes and navigate without advertising, sponsored results, analytics, account tracking or location history.

## Implemented in source

- Current position using Google Play services Fused Location Provider, with Android GPS/network fallback and a user switch to disable enhanced location.
- OpenStreetMap-derived vector map using MapLibre GL JS + the standard OpenFreeMap **Bright** style.
- Useful OpenFreeMap place labels are visible by default, with a local Layers control to hide them. No sponsored markers or advertising are injected.
- Optional cycling-infrastructure overlay when the map source exposes cycleways.
- UK address/place search through TomTom Search, triggered only by explicit user search.
- Floating search bar with live suggestions, Enter-to-search, a Star menu for Home/starred places, bottom place sheet and bottom route sheet.
- Local starred places with add/remove controls; no cloud account required.
- Layers sheet for traffic, cycling infrastructure and place labels.
- Places chooser includes personal, food/drink, shopping/services, transport and useful-nearby categories such as cafés, bakeries, EV charging, parking, railway stations, bus stops, public toilets, hospitals, hotels, parks, playgrounds, gyms, libraries and cinemas.
- Driving/active-travel routes use a blue selected route; public-transport routes use consistent per-mode colours with desaturated alternatives. Tap a result card to switch the highlighted route.
- Pre-navigation Steps sheet for turn-by-turn route review.
- Integrated route-planner dropdown inside the main **Where to?** box: once Directions starts, the destination remains in the top box with a clear X; tapping it reveals My location, added stop(s), destination and the currently selected route without permanently covering the map.
- Route points are directly editable: the start can be replaced with any searched location for remote journey planning, every point can be replaced or drag-reordered — including **My location** and the final destination — and **My location** can be restored before starting live navigation.
- Cancelling or superseding a route invalidates the active native request and cancels public-transport background work, preventing an abandoned slow journey search from updating a later route.
- Public-transport journeys now have a **Start** action and in-app stage-by-stage navigation for walking, boarding, riding/transferring and alighting, with the active stage colour carried into the navigation banner.
- Driving route preferences for avoiding motorways, toll roads and ferries.
- Tap useful labelled places or press-and-hold anywhere on the map to select a destination, without an unnecessary confirmation toast.
- Locally stored Home shortcut.
- **Driving routing through TomTom**, including live traffic, incidents/restrictions known to TomTom and speed-limit sections where available.
- **Walking and cycling routing through Valhalla/OpenStreetMap with safety/comfort-biased costing**, rather than hard-coded local bridge/road exceptions. Cycling heavily penalises ordinary roads when paths/cycleways are available; walking favours walkways and pavements and penalises driveways/alleys/service access.
- No hard-coded Bristol bridge/road exclusions.
- Driving choices labelled Fastest now / Usual route / Alternative where available; active-travel routes show a path-preferred route plus an alternative where available.
- Dedicated active-navigation UI with heading-up follow camera, directional location marker, manoeuvre arrow, written turn instruction, remaining time/distance and selected route line.
- 2D/3D map-view toggle.
- Free map panning/zooming during navigation. The normal blue location button appears only after follow mode has been suspended and acts as **Recentre**.
- Compact icon-only Drive / Cycle / Walk selectors.
- Turn-by-turn voice, large peripheral edge-flash or silent alert mode.
- Selectable installed Android TTS engine and voice with preview.
- Automatic rerouting using route-segment projection and repeated off-route confirmation.
- On-route Reroute now and Avoid road ahead controls.
- Rural GPS jump rejection plus route-line display snapping.
- Current driving speed and TomTom-provided legal speed limit shown in mph during navigation when available.
- Foreground navigation service and notification only while actual navigation is active.
- Screen remains awake whenever OpenRoad is in the foreground.
- Settings reorganised into sections with a permanently visible Done button.
- No app account, ads, analytics, Firebase or advertising ID integration.
- No route/search history database. Only the currently active route is kept in temporary app cache for recovery and is cleared on normal stop/arrival.
- TomTom API key is pre-seeded for this personal build and copied into Android Keystore on first launch. Do not distribute the APK/source publicly with that key embedded.
- Public-transport credentials (BODS, TfL, Rail Data Marketplace and TransportAPI) are stored through Android Keystore rather than ordinary preferences.
- Normal English bus journey planning uses the private pre-indexed OpenRoad Transport Server first; the DfT regional GTFS on-device cache remains as an automatic fallback. NaPTAN stop-area data is cached for seven days.
- The private transport server no longer uses a reusable bearer token. OpenRoad pairs once using a short-lived code, generates an EC signing key inside Android Keystore, and signs every HTTPS POST request; the server stores only the device public key and anti-replay metadata.
- Public-transport journey cards distinguish **Live**, **Mixed live/scheduled**, and **Scheduled** data rather than presenting network-fetched timetable data as live.
- Public-transport results are deliberately limited to the best **three** for the selected **Quickest / Balanced / Fewest changes** priority. Walking remains part of journey time/ranking but is no longer a user-configured hard exclusion.
- Transit route lines and stop dots are map-anchored MapLibre geometry; background live/geometry enrichment is deferred until a pan/zoom gesture has ended so the overlay does not drift or jump while the map is being inspected.
- Search-location bias is off by default.

## Active-travel routing note

Walking and cycling use the public FOSSGIS Valhalla service over OpenStreetMap data. OpenRoad deliberately chooses comfort/safety-biased dynamic costing instead of the nominal fastest route. It identifies itself and throttles requests to respect the public service's fair-use limits.

No routing engine can guarantee that every path, bridge, temporary closure or access restriction is current. OpenStreetMap/Valhalla data still needs real-world testing, and signs/barriers on the ground remain authoritative. The v0.6.25 build keeps safety-biased active-travel routing and makes the public-transport layer server-first without making the server a single point of failure. London journeys use TfL directly. Bristol/South-West is permanently prepared on the private server; other English regions are prepared only when a destination, manual preload, or optional daily location check needs them. The daily check is skipped while any navigation is active. Scheduled journey choices return first; exact walking geometry and live BODS vehicle data are enriched afterwards. TransportAPI remains optional fallback only and is disabled by default.

## Not yet implemented

- DfT Street Manager / National Highways / Scotland / Wales government roadworks/closure integration.
- Cycling elevation profile.
- Offline maps/offline routing.
- Lane-level/commercial-SDK-grade map matching and lane guidance.
- Fully native MapLibre renderer (the current renderer is packaged MapLibre GL JS in a hardened Android WebView).

## Building

Open the project folder in Android Studio and select **Build > Build APK(s)**, or connect the test phone and press **Run**. MapLibre GL JS/CSS is downloaded during the build and packaged inside the APK; OpenFreeMap supplies the online Bright style/vector tiles at runtime.

See `docs/BUILD_AND_INSTALL.md`, `docs/TEST_STATUS.md`, `docs/CHANGES_0.6.25.md`, and `docs/SERVER_DEPLOYMENT_0.6.24.md`.


## Public-transport credentials

No credential is required for NaPTAN, DfT/BODS scheduled GTFS downloads, or normal low-volume TfL Unified API access. For the full live/fallback feature set, OpenRoad can additionally use a BODS API key (fresh English bus vehicle positions), a Rail Data Marketplace **Live Departure Board Consumer key** (official Darwin live rail predictions), and TransportAPI app_id/app_key (GB-wide multimodal fallback planning). A TfL app key is optional and only raises the request allowance above anonymous access. Personal-build fields are present for all of these credentials and, when populated, are copied into Android Keystore on first launch.


## Credential audit
The personal build re-seeds the owner-supplied TomTom, BODS, TfL and TransportAPI credentials once on upgrade so stale/manual values from earlier builds cannot remain active. Settings shows masked stored values with an explicit reveal control. TfL secondary is stored as a rotation spare and is not sent unless the primary is replaced manually.

TransportAPI authentication and product access are separate: a 403 stating that an endpoint is not part of the plan means the app_id/app_key were recognised but the account plan does not include TAPI Journey Planner.
