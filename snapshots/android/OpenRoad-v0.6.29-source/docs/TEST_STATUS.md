# Test status — ClearRoute 0.2.2

## Checks performed in this generation environment
- JavaScript syntax checked with Node (`node --check`).
- All Android XML resources parsed as XML.
- Required project/source files checked by `validate.sh`.
- Java source passed a `javac` syntax smoke test: compilation cannot resolve Android/JSON classes here because the Android SDK is absent, but no Java grammar/syntax errors were reported before dependency resolution errors.
- Native ↔ JavaScript callback names and the new navigation DOM element IDs were cross-checked.
- Source scanned for stale permanent active-route storage and precise-coordinate diagnostic logging.

## Device evidence from earlier builds
Earlier v0.1.x builds were installed and exercised by the user on real Android phones. Those tests established that the map, search, route calculation, GPS acquisition, voice output and destination selection could run, and exposed the visual-guidance defect that prompted this audit.

## Not performed here for v0.2.2
- APK compilation: the execution environment does not contain the Android SDK/build toolchain.
- Physical Android installation of v0.2.2.
- Live TomTom requests: the user's API key is intentionally not present here.
- Live driving/walking/cycling navigation and reroute test.

Therefore v0.2.2 is an **audited source build awaiting Android Studio/device validation**, not a claimed finished APK.


## v0.3.0 source validation

Validated in the build-generation environment:
- JavaScript syntax (`node --check`)
- Android XML parsing
- source feature guards in `validate.sh`
- native/JavaScript bridge method presence
- Java grammar smoke test (Android symbols unavailable without Android SDK)

Still requires Fairphone road testing:
- bus-lane/restricted-access behaviour;
- manual avoid-ahead detours;
- rural GPS stability;
- speed-limit coverage/accuracy;
- speed display;
- final brighter map palette.

Do not treat provider speed limits or road-closure data as infallible; normal road signs and restrictions remain authoritative.

## v0.5.0 source validation

Validated in the generation environment:
- JavaScript syntax (`node --check`)
- Android XML parsing
- required DOM/native wiring and v0.5 feature guards in `validate.sh`
- absence of the previous hard-coded Bristol active-travel exclusions
- Valhalla active-travel routing configuration and fair-use throttle presence
- Java grammar smoke test (full Android compilation still requires the Android SDK)

Still requires Fairphone route testing. In particular, test walking/cycling routes you know well and compare whether dedicated paths, cycleways and pedestrian infrastructure are now preferred appropriately. Provider/OSM data can still be incomplete, so signs, closures and physical barriers remain authoritative.

## v0.6.0 source validation
- Rebuilt map-first UI IDs checked against JavaScript references.
- JavaScript syntax checked with Node.
- Android XML parsed.
- Java parser-style smoke test run through `javac` where available (Android symbols intentionally unresolved without the Android SDK).
- Verified route layers, route-line selection, saved places, route Steps, Layers sheet, navigation quick controls, arrival time and driving avoidances are wired.
- Verified v0.5 active-travel safety-biased Valhalla routing and privacy checks remain present.
- Physical-device visual/interaction testing is still required; this environment cannot run the Android APK.

## v0.6.1 source validation

- Live search suggestion dropdown wiring checked.
- Search-current-map-area bridge and TomTom bounding-box request checked.
- Labelled area-result marker lifecycle checked (replace/clear/select).
- Stale suggestion and stale area-search request IDs are invalidated when the query changes.
- `node --check`, Android XML parsing, Java grammar smoke test, and project feature validation pass.
- Physical Android/WebView interaction still requires device testing.


## v0.6.2 source validation
- Enter-to-search + Start menu structure validated.
- Category-aware search result/pin icon plumbing validated.
- Settings fixed-footer layout and grouped panels validated.
- JavaScript syntax and Android XML validated.

## v0.6.3 source validation
- Star menu structure and Home-first ordering validated.
- Along-route TomTom POST search, remaining-route geometry trimming and detour fields wired.
- Intermediate-stop routing is wired for TomTom driving and Valhalla walking/cycling.
- Navigation service reloads an inserted waypoint without ending navigation and preserves it during reroutes until reached.
- Official Shazam package launcher is wired; ClearRoute navigation service remains active while Shazam is foregrounded.
- JavaScript syntax, Android XML and Java grammar smoke tests pass in the available environment.


## OpenRoad v0.6.5 source validation

Validated in the generation environment:
- JavaScript syntax (`node --check`).
- Android XML parsing.
- Full `validate.sh` feature/source guard set.
- Every static `el('…')` JavaScript DOM reference resolves to an HTML element ID.
- SVG close/back controls are present on the relevant place/route/sheet controls.
- Along-route callout structure, leader line, exact-location dot and collision-layout hooks are present.
- Dense synthetic marker-layout checks found non-overlapping placements for clusters up to ten same-point callouts at a representative phone viewport; larger clusters degrade by minimising overlap rather than stacking every label in one position.
- TomTom Orbis v2 flow and incident tile URL forms retained.
- Java grammar smoke test performed by `validate.sh`; full Android compilation still requires Android Studio/SDK.

The Android application ID remains `uk.co.bengoodman.clearroute` intentionally, so OpenRoad v0.6.5 can update the existing installation and retain its local data. Physical-device testing is still required for final visual spacing at different zoom levels and screen sizes.

## OpenRoad v0.6.7 source validation

Validated in the generation environment:
- JavaScript syntax (`node --check`).
- Android XML parsing and the full `validate.sh` feature/source guard set.
- Provider-setting DOM IDs and native bridge calls cross-checked.
- Android-Keystore-backed storage paths checked for BODS, TfL, Darwin and TransportAPI secrets.
- Official-source routing paths checked for TfL, BODS SIRI-VM, DfT GTFS, NaPTAN and National Rail Darwin.
- DfT GTFS route-number matching now selects the candidate route nearest the current location, avoiding collisions between common line numbers in different towns.
- Scheduled/live labelling is deliberately conservative: BODS vehicle position alone does not become a predicted arrival time.
- Java grammar smoke test is performed by `validate.sh`; full Android compilation still requires Android Studio/SDK.

Physical-device and live-provider testing is still required, particularly initial GTFS download size/time, provider credential acceptance, London TfL journeys, Darwin enrichment, and live BODS vehicle overlays.

## OpenRoad v0.6.8 source validation

Validated in the generation environment:
- JavaScript syntax (`node --check`) and Android XML parsing.
- Full `validate.sh` feature/source guard set.
- Public-transport results UI: Quickest/Balanced/Fewest changes, per-mode colour chips, separate info controls and selected-route switching.
- Selected transit route legs use saturated per-mode colours; alternatives use desaturated per-mode colours with no transport-mode markers on the map.
- Intermediate public-transport stops are passed as real routing waypoints and combined into whole-journey alternatives.
- Public-transport mode selections are passed to TfL and TransportAPI where their current journey APIs support them; TfL also receives walking and accessibility preferences.
- Bus-service view retains Back state, published stops/timetable and up to three nearest fresh live bus positions when coordinates are available.
- BODS GTFS calendar handling now distinguishes a genuine zero-service day from a feed with no service calendar, preventing inactive trips from being shown as departures.
- Bundled TomTom credential one-time re-seed path checked for versionCode 68; supplied public-transport credentials remain Keystore-seeded.
- Static DOM/native wiring checks and Java grammar smoke test pass.

A full Android compile cannot be performed in this generation environment because the Android SDK/Gradle toolchain is not installed. Android Studio/device testing is still required for provider-side credential acceptance, live network responses, bottom-sheet touch behaviour and final phone-size layout.


## OpenRoad v0.6.9 source validation
- JavaScript syntax checked after starred-place rename and zoom-scaling changes.
- HTML IDs and JavaScript references checked for the new favourite-name sheet.
- TransportAPI request construction audited against the current Journey Planner example.
- Destination pin anchor changed to an SVG tip-aligned marker.
- Archive integrity and project validation re-run before packaging.

## OpenRoad v0.6.11 source validation
- Removed TransportAPI from the default public-transport routing path; the fallback is off unless explicitly enabled in Public transport settings.
- Added `BodsJourneyPlanner`, an on-device official DfT/BODS GTFS router for English bus journeys outside London.
- Synthetic GTFS functional tests passed for both a direct bus journey and a one-change same-stop interchange, including walking access/egress, timetable times, route geometry and result JSON structure.
- The planner honours maximum walking, walking speed, transfer buffer and Quickest/Balanced/Fewest changes ranking.
- BODS live-position enrichment remains separate from scheduled routing, so live vehicle positions do not become false arrival predictions.
- `TransitClient` and the new planner passed semantic Java compilation against Android/JSON/XMLPull-compatible stubs, in addition to `validate.sh`, JavaScript syntax and Android XML checks.
- Full Android APK compilation still requires Android Studio/Android SDK; live BODS download performance and real-world timetable coverage require phone testing.


## OpenRoad v0.6.12 source validation
- Driving default verified in JavaScript startup and new-destination flow.
- Public transport is only prepared after explicit Public-mode selection.
- Timetable-first/live-later callback path added; live updates preserve selected route.
- BODS exact shape geometry is staged after the first timetable paint.
- Regional BODS metadata uses in-memory cache and synchronised regional file preparation.
- Bottom-sheet minimised state raised above the Android safe-area and enlarged for reliable restoration.
- JavaScript syntax, XML parsing, source feature validation and Java grammar smoke tests are run by `validate.sh`.


## OpenRoad v0.6.13 server-first transport checks

- Private OpenRoad server client added with short connection/read timeouts and automatic on-device fallback.
- Selecting Public transport no longer starts the local regional GTFS preparation when the private server is configured.
- Server-planned journeys retain staged BODS live enrichment without requiring the phone to parse `shapes.txt`.
- Server URL and masked/revealable token are visible in Settings.


## OpenRoad v0.6.14 private-server security checks

- Reusable `BUNDLED_OPENROAD_SERVER_TOKEN` removed from the Android build.
- Device EC P-256 key generated via Android Keystore.
- Pairing uses a server-generated short-lived, one-time code.
- Normal API calls are signed HTTPS POST requests and include timestamp + nonce replay protection.
- Journey coordinates are in the POST body rather than URL query parameters.
- Server client falls back to on-device BODS planning until securely paired.
- Settings exposes pair/check/remove controls but no private server signing key.
- `DeviceAuth.java` and `OpenRoadServerClient.java` compile successfully against Android-compatible Java stubs in the development audit.

## OpenRoad v0.6.17 routing audit
- Opening location-centre path checked for both map-first-load and first-location-fix orderings.
- Initial result limit verified at three; public-transport Load more increments by three to a hard cap of nine.
- Private server v0.2.1 PHP files pass `php -l`.
- Audited nearest-stop selection, reachable boarding time, total walking budget, direct journeys, one-change journeys, transfer margins and route ranking.
- Fixed the v0.2.0 nearest-stop SQL LIMIT ordering defect and the local fallback's same-trip upstream-stop preference.
- Balanced/Quickest/Fewest-changes scoring is aligned between server, local fallback and Android display ordering.
- Exact BODS shape geometry is preferred for bus legs; walking geometry is independently refined against the pedestrian router after first paint.
- Live bus positions remain opt-in in the bus-service view and are not on the critical route/timetable response path.
- Full Android APK compilation still requires Android Studio/SDK and real-device/public-feed testing remains the final validation.


## OpenRoad v0.6.21 source validation
- Re-validated the v0.6.20 foreground-service/active-route persistence path for driving, cycling, walking and public-transport navigation.
- Verified Activity pause/destroy paths do not clear the active route or stop either navigation service; resume reloads the stored route and re-establishes the appropriate foreground service.
- Layers/Places remains reachable through `navLayersBtn` in every navigation mode.
- The single location control is moved into the navigation-side flex stack while navigating, removing the v0.6.20 independent mid-screen placement that could overlap another right-hand control on shorter viewports.
- Recentre uses the same plain blue dot and 48 px hit area as intended in v0.6.20.
- JavaScript syntax, HTML parsing, Android XML parsing, Java grammar smoke checks and the expanded `validate.sh` regression suite pass in this environment.
- A full Android APK compile and physical lock/unlock navigation test still require Android Studio/SDK and a real Android device.

## OpenRoad v0.6.22 source validation

Validated 12 October 2026 from the v0.6.21 source baseline after the public-transport overlay/ranking changes.

- `node --check app/src/main/assets/app.js`: passed.
- HTML parser smoke test for `index.html`: passed.
- Android XML parsing in `validate.sh`: passed.
- Project feature/source assertions in `validate.sh`: passed, including map-anchored transit stop layers, deferred overlay refresh during map gestures, removal of the Maximum walking UI/filter, and fixed three-result ranking.
- `javac` parser/grammar smoke test in `validate.sh`: no Java parser errors (Android SDK symbols are intentionally unavailable in this environment).
- Full Android APK compilation/install and physical pinch-zoom testing remain device/Android-Studio tests; they cannot be completed in this source-validation environment.

## OpenRoad v0.6.23 source validation

Validated 13 October 2026 from the v0.6.22 source baseline after the route-lifecycle, route-point and Places changes.

- `node --check app/src/main/assets/app.js`: passed.
- Project feature/source assertions in `validate.sh`: passed.
- Java grammar smoke test in `validate.sh`: passed (Android SDK symbols are intentionally unavailable in this environment).
- Route cancellation is guarded independently in JavaScript by request ID, in `MainActivity` by `latestRouteRequestId`, and in `TransitClient` by a cancellable active `Future` plus generation token/checkpoints.
- Custom-origin routing paths are present for direct routes, one-stop road/active-travel routes and multi-stop public-transport routes, so route planning no longer requires the phone's current position when a start place has been chosen explicitly.
- Multi-stop transit initial planning now requests fast-phase server results segment-by-segment before slower full/enrichment work.
- Route-point stop replacement/reordering and the expanded Places category set are covered by source assertions.
- Full Android APK compilation/install, touch-drag testing, real public-transport timing and cancellation during an in-flight network request remain Android Studio/real-device tests.

## OpenRoad v0.6.24 source validation

Static validation covers the combined origin/via/destination reorder model; MapLibre-anchored bus route stop dots and hit layer; clickable bus stops; fixed Places Apply footer; route-sheet handle spacing; app-consistent driving Route Options; Rail Data Marketplace Consumer-key storage and `x-apikey` request authentication; source versioning; JavaScript syntax; Android XML; and Java grammar smoke testing where `javac` is available.

Real-device checks still required: drag every route point through first/middle/last positions; pinch-zoom a bus route repeatedly and verify its stop dots remain on the route; tap several bus stops and confirm the services sheet is useful; verify Places Apply stays visible during a long category scroll; test the route-sheet minimise handle around the transport-mode controls; and validate Rail Data Marketplace responses with the user's own Consumer key.
