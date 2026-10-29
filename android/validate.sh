#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

node --check "$ROOT/app/src/main/assets/app.js"

python3 - <<'PY' "$ROOT"
import os, sys, xml.etree.ElementTree as ET
root=sys.argv[1]
required=[
 'settings.gradle','build.gradle','gradle.properties','app/build.gradle','app/src/main/AndroidManifest.xml',
 'app/src/main/java/uk/co/bengoodman/clearroute/MainActivity.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/NavigationService.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/TransitNavigationService.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/RouteMath.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/ActiveRouteStore.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/SecureStore.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/BodsGtfsCache.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/BodsJourneyPlanner.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/TransitPreloadReceiver.java',
 'app/src/main/java/uk/co/bengoodman/clearroute/TransitPreloadBootReceiver.java',
 'app/src/main/assets/index.html','app/src/main/assets/app.js','app/src/main/assets/styles.css']
missing=[p for p in required if not os.path.exists(os.path.join(root,p))]
if missing: raise SystemExit('Missing: '+', '.join(missing))

for base, _, files in os.walk(os.path.join(root,'app','src','main')):
    for name in files:
        if name.endswith('.xml'):
            ET.parse(os.path.join(base,name))

html=open(os.path.join(root,'app/src/main/assets/index.html'),encoding='utf-8').read()
js=open(os.path.join(root,'app/src/main/assets/app.js'),encoding='utf-8').read()
css=open(os.path.join(root,'app/src/main/assets/styles.css'),encoding='utf-8').read()
for element_id in ['topUi','starBtn','starMenuDropdown','starMenuItems','searchSuggestionsDropdown','searchSuggestions','modeSwitch','driveBtn','cycleBtn','walkBtn','mapActions','layersBtn','locateBtn','destinationCard','saveDestinationBtn','routeCard','routePreferencesBtn','routePreferences','showStepsBtn','stepsSheet','savedSheet','layersSheet','navManeuverIcon','navUi','navMapActions','navSoundBtn','navAlongRouteBtn','navOverviewBtn','viewToggleBtn','navViewToggleBtn','arrivalTime','edgeFlash','alongRouteSheet','alongRouteResults','shazamBtn','settings','closeSettingsBtn']:
    if f'id="{element_id}"' not in html:
        raise SystemExit(f'Missing HTML id: {element_id}')
if 'id="recenterBtn"' in html or "el('recenterBtn')" in js:
    raise SystemExit('Obsolete separate Recentre button/reference still present')
if 'Point selected. Tap Directions to navigate.' in js:
    raise SystemExit('Dropped-pin notification/toast should not be present')

main=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/MainActivity.java'),encoding='utf-8').read()
nav=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/NavigationService.java'),encoding='utf-8').read()
active=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/ActiveRouteStore.java'),encoding='utf-8').read()
api=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java'),encoding='utf-8').read()
transit=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java'),encoding='utf-8').read()
gtfs=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/BodsGtfsCache.java'),encoding='utf-8').read()
planner=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/BodsJourneyPlanner.java'),encoding='utf-8').read()
secure=open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/SecureStore.java'),encoding='utf-8').read()
gradle=open(os.path.join(root,'app/build.gradle'),encoding='utf-8').read()

checks={
 'OpenRoad visible identity': '<string name="app_name">OpenRoad</string>' in open(os.path.join(root,'app/src/main/res/values/strings.xml'),encoding='utf-8').read() and '<title>OpenRoad</title>' in html and 'OpenRoad 0.6.38' in html,
 'bundled personal TomTom key field': 'BUNDLED_TOMTOM_API_KEY' in gradle and 'SecureStore.saveApiKey' in main,
 'v0.6.38 version': "versionName '0.6.38'" in gradle and 'versionCode 98' in gradle and 'OpenRoad-Android-Build/0.6.38' in gradle,
 'bearing forwarded': 'o.put("hasBearing"' in main,
 'maneuver forwarded': 'o.put("maneuver"' in main,
 'route segment projection': 'RouteMath.project(route' in nav,
 'cache active route': 'getCacheDir()' in active,
 'request-id route guard': 'latestRouteRequestId' in main,
 'dedicated navigation chrome': 'setNavigationChrome(true)' in js,
 'navigation layers always available': 'navLayersBtn' in html and "show('navMapActions', active)" in js and "el('navLayersBtn').onclick" in js,
 'lock-safe transit navigation': 'TransitNavigationService' in main and 'ensureTransitNavigationService' in main and 'ActiveRouteStore.save(MainActivity.this, state)' in main and 'START_STICKY' in open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/TransitNavigationService.java'),encoding='utf-8').read(),
 'even navigation control stack': '.nav-map-actions{right:14px;gap:10px;align-items:center}' in css and '.nav-map-actions .locate-button' in css and 'navigation-recentre' not in js,
 'default bright map': "style:'https://tiles.openfreemap.org/styles/bright'" in js,
 'cycleway overlay': 'ensureCyclewayLayer' in js and 'clearroute-cycleways' in js,
 'free navigation pan': 'navigationFollow = false' in js and 'recentreNavigation' in js,
 'single location/recentre control': 'syncLocateButtonHost' in js and "const target=navigating ? navigationHost : normalHost" in js and 'recentreNavigation();' in js and 'recenter-mode' in css,
 '2d 3d toggle': 'toggleMapView' in js and 'angledView' in js,
 'tts init guard': 'ttsReady' in nav and 'speakNavigation(' in nav,
 'navigation audio usage': 'USAGE_ASSISTANCE_NAVIGATION_GUIDANCE' in nav,
 'updated API user agent': 'OpenRoad/0.6.38' in api,
 'speed limit forwarding': 'speedLimitKmh' in main and 'speedLimitKmhAt' in nav,
 'manual reroute controls': 'ACTION_AVOID_AHEAD' in nav and 'avoidRoadAhead' in main and 'avoidAheadBtn' in html,
 'rural GPS filtering': 'isPlausibleLocation' in nav and 'pointAtOffset(route, progress)' in nav,
 'always awake': 'FLAG_KEEP_SCREEN_ON' in main and 'clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)' not in main,
 'Valhalla active travel': 'https://valhalla1.openstreetmap.de/route' in api and 'requestActiveTravelRoute' in api,
 'cycling paths preference': 'bicycle.put("use_roads", 0.05)' in api and 'bicycle.put("use_living_streets", 0.9)' in api,
 'walking infrastructure preference': 'pedestrian.put("walkway_factor", 0.55)' in api and 'pedestrian.put("sidewalk_factor", 0.72)' in api,
 'active travel fair-use throttling': 'Thread.sleep(wait)' in api and 'X-Client-Id' in api,
 'no Bristol hard-coded routing': 'Vauxhall Bridge' not in api and 'Cumberland' not in api and 'Ashton Avenue' not in api,
 'route-sheet travel modes': html.count('class="mode mode-icon') == 4 and 'transitBtn' in html and 'route-sheet' in html,
 'map-first search': 'search-pill' in html and 'starBtn' in html and 'quickActions' not in html,
 'enter-only full search': "e.key==='Enter'" in js and 'searchBtn' not in html,
 'starred places menu': 'starMenuDropdown' in html and 'renderStarMenu' in js and 'Home' in js and 'Starred place' in js,
 'category search symbols': 'searchResultCategory' in js and 'result-symbol' in css and 'area-search-pin' in css,
 'clean settings panels': html.count('class="settings-panel"') >= 4 and 'settings-item-copy' in css,
 'search suggestion dropdown': 'searchSuggestionsDropdown' in html and 'requestSearchSuggestions' in js and 'onSearchSuggestions' in js,
 'search current map area': 'Search current map area' in js and 'searchMapArea' in main and 'topLeft=' in api and 'btmRight=' in api,
 'labelled map search pins': 'area-search-marker' in js and 'area-search-label' in css and 'showAreaSearchResults' in js,
 'google-like route styling': '#1a73e8' in css and 'route-line-' in js and 'route-hit-' in js,
 'layers sheet': 'layersSheet' in html and 'trafficLayerBtn' in html and 'cycleLayerBtn' in html and 'placesLayerBtn' in html,
 'saved places ui': 'savedSheet' in html and 'saveDestinationBtn' in html and 'removeFavourite' in main,
 'steps preview': 'stepsSheet' in html and 'showRouteSteps' in js,
 'arrival time': 'arrivalTime' in html and 'formatArrivalTime' in js,
 'navigation quick alerts': 'navSoundBtn' in html and 'cycleNavAlertMode' in js,
 'route overview': 'navOverviewBtn' in html and 'showRouteOverview' in js,
 'driving route avoidances': 'avoidMotorways' in html and 'setRouteAvoidances' in main and '&avoid=motorways' in api and '&avoid=tollRoads' in api and '&avoid=ferries' in api,
 'along-route search': 'searchAlongRoute' in main and 'searchAlongRoute/' in api and 'navAlongRouteBtn' in html and 'alongRouteSheet' in html,
 'along-route waypoint': 'addAlongRouteStop' in main and 'routeViaSync' in api and 'ACTION_RELOAD_ROUTE' in nav,
 'shazam launcher': 'openShazam' in main and 'com.shazam.android' in main and 'shazamBtn' in html,
 'blue-dot locate icon': 'locate-dot-icon' in html and '.locate-dot-icon' in css,
 'sticky settings footer': 'settings-footer' in html and '.settings-footer' in css and 'flex:0 0 auto' in css,
 'contacts address search': 'READ_CONTACTS' in open(os.path.join(root,'app/src/main/AndroidManifest.xml'),encoding='utf-8').read() and 'getContactMatches' in main and 'onContactGeocoded' in js,
 'public transport routing': 'TransitClient.route' in main and 'TransportAPI' in html and 'transitBtn' in html,
 'official transit broker': 'requestTflJourney' in transit and 'parseBodsBusVehicles' in transit and 'enrichDarwin' in transit and 'cacheNaptanAreaAsync' in transit,
 'BODS schedule cache': 'BodsGtfsCache.findBusRoute' in transit and 'gtfs-file/' in gtfs and 'routes.txt' in gtfs and 'trips.txt' in gtfs and 'shapes.txt' in gtfs,
 'local BODS journey planner': 'BodsJourneyPlanner.plan' in transit and 'one same-stop interchange' in planner and 'transportApiFallback' in js,
 'device-signed private server transit': 'OpenRoadServerClient.route' in transit and 'BUNDLED_OPENROAD_SERVER_URL' in gradle and 'BUNDLED_OPENROAD_SERVER_TOKEN' not in gradle and 'openRoadPairingCode' in html and 'pairOpenRoadServer' in main and os.path.exists(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/DeviceAuth.java')),
 'live-vs-scheduled labels': 'clearRouteDataStatus' in transit and 'timeStatus' in transit and 'transit-status-live' in js,
 'secure public transport credentials': 'saveSecret' in secure and 'SECRET_BODS_KEY' in main and 'SECRET_TFL_KEY' in main and 'SECRET_DARWIN_USER' in main and 'SECRET_TRANSPORTAPI_KEY' in main,
 'provider settings split': 'NaPTAN stops & stations' in html and 'DfT bus data · BODS / GB GTFS' in html and 'National Rail · Rail Data Marketplace' in html and 'TransportAPI · optional fallback' in html,
 'transit coloured route stages': 'TRANSIT_COLORS' in js and 'TRANSIT_ALT_COLORS' in js and 'transit-stage-strip' in js,
 'transit ranking slider': 'Quickest' in html and 'Balanced' in html and 'Fewest changes' in html and 'transitPreference' in js,
 'transit mode filters': 'data-transit-mode="bus"' in html and 'routeAllowedByTransitSettings' in js and 'tflModes(settings)' in transit and 'transportApiModes(settings)' in transit and 'service=silverrail' in transit,
 'transit info sheet': 'transitDetailSheet' in html and 'showTransitDetail' in js,
 'bus service view': 'busServiceSheet' in html and 'renderBusServiceContent' in js and 'slice(0,3)' in js,
 'integrated route planner via stops': 'routePlannerDropdown' in html and 'calculateTransitRouteWithStops' in main and 'calculateRouteViaStop' in main and 'routeWithStops' in transit,
 'public transport navigation': 'startTransitNavigation' in js and 'updateTransitNavigation' in js and "mode==='transit'" in js,
 'sheet minimisation': 'toggleSheetMinimised' in js and '.bottom-sheet.minimised' in css and "sheet.classList.contains('minimised')" in js,
 'route planner outside-tap collapse': "!e.target?.closest?.('#topUi')" in js and "hideStarMenu(); closeRoutePlanner();" in js,
 'explicit saved-place naming': 'renameDestinationBtn' in html and 'renameCurrentDestination' in js and "rename.textContent='Rename'" in js,
 'transit walking street geometry': 'enrichWalkingGeometry' in transit and 'ApiClient.routeSync(context, aLat, aLon, bLat, bLon, "walk")' in transit,
 'BODS timetable': 'loadUpcomingTimetable' in gtfs and 'calendar_dates.txt' in gtfs and 'hasServiceCalendar' in gtfs,
 'TomTom reseed repair': 'PREF_BUNDLED_TOMTOM_REVISION' in main and 'bundledRevision < 610' in main and 'PREF_BUNDLED_TRANSIT_REVISION' in main,
 'motorway preference': 'preferMotorways' in html and 'isPreferMotorways' in main and 'Motorway-heavy' in api,
 'place details': 'requestPlaceDetails' in main and 'onPlaceDetails' in js,
 'along-route collision callouts': 'layoutAlongRouteMarkers' in js and 'along-route-callout' in css and 'along-route-leader' in css and 'along-route-point' in css,
 'starred map markers': 'starred-map-marker' in js and 'renderStarredMarkers' in js,
 'regional transit preloading': 'prepareTransitDestination' in main and 'dailyTransitPreloadToggle' in html and 'preloadTransitArea' in main and 'TransitPreloadReceiver' in main,
 'places category chooser': 'placesSheet' in html and 'data-place-category="pubs"' in html and 'PLACE_CATEGORY_META' in js and 'requestPlaceCategory' in js,
 'bus stop interaction': 'lookupBusStop' in main and 'openBusStop' in js and 'Next 3 live buses' in js,
 'transit stable route selection': 'selectedRouteId' in js and 'clearRouteId' in js and 'drawRoutes(navigating)' in js,
 'transit map-anchored stop dots': 'renderTransitStopLayer' in js and "type:'circle'" in js and 'route-transit-stop-dots' in js and 'transit-stop-map-marker' not in css,
 'transit overlay gesture stability': 'pendingTransitOverlayRefresh' in js and 'map?.isMoving?.()' in js and "map.on('moveend', ()=>" in js,
 'no public transit walking cap': 'transitMaxWalk' not in html and 'Maximum walking' not in html and 'delete legacy.maxWalk' in js and 'walkBudgetSec' not in planner,
 'exactly three ranked transit results': 'const TRANSIT_RESULT_LIMIT = 3' in js and 'Load 3 more' not in js and '.put("resultLimit", 3)' in open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java'),encoding='utf-8').read(),
 'route-request cancellation': 'cancelRouteRequests' in main and 'cancelActiveRouteRequest' in js and 'cancelRouteWork' in transit and 'ROUTE_GENERATION' in transit,
 'custom route origin': 'routePointList' in html and 'originOverride' in js and 'calculateRouteFrom' in main and 'calculateTransitRouteWithStopsFrom' in main,
 'editable route points': 'routePlannerPoints' in js and 'commitRoutePointReorder' in js and 'planner-route-point-drag' in js and "beginRoutePointSearch(isFirst?'origin':isLast?'destination':'via'" in js,
 'expanded places chooser': 'data-place-category="evcharging"' in html and 'data-place-category="toilets"' in html and 'data-place-category="libraries"' in html and 'PLACE_CATEGORY_META' in js,
 'all route points reorderable': 'points.splice(from,1)' in js and 'applyRoutePointOrder(points)' in js and 'planner-route-point-drag' in css,
 'pin destination detail': "point?.name==='Pin'" in js and 'isCoordinateText(address)' in js,
 'bus route map-anchored stops': 'bus-route-stop-dots' in js and 'bus-route-stop-hit' in js and 'busRouteStopData' in js,
 'fixed places apply footer': '.places-card>#applyPlacesBtn{flex:0 0 auto' in css and '.places-card>.places-choice-list{flex:1 1 auto' in css,
 'safer route minimise spacing': '.route-sheet:not(.minimised){padding-top:24px}' in css and '.route-sheet.transit-active:not(.minimised) .mode-switch{margin-top:4px}' in css,
 'app-style driving route options': 'route-preferences-panel' in html and 'settings-switch' in html and '.route-preferences-panel .settings-item' in css,
 'Rail Data Marketplace server proxy': 'railDataKeyMasked' in html and 'OpenRoadServerClient.railDepartureBoard' in main and '/api/v1/rail.php' in open(os.path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java'),encoding='utf-8').read() and 'BUNDLED_DARWIN_USERNAME' in gradle,
 'Phase 2 read-only rail board': 'railDepartureBoard' in main and 'checkRailDepartures' in main and 'railDepartureResults' in html and 'onRailDepartures' in js,
}
failed=[k for k,v in checks.items() if not v]
if failed: raise SystemExit('Feature validation failed: '+', '.join(failed))

# Avoid reintroducing the privacy bug where precise coordinates were written to Logcat.
for line in (main+'\n'+nav).splitlines():
    if 'Log.' in line and ('getLatitude()' in line or 'getLongitude()' in line):
        raise SystemExit('Precise coordinates found in diagnostic log line: '+line.strip())
print('OpenRoad source validation passed.')
PY

# We cannot compile Android classes without an Android SDK here. If javac exists, still use
# it as a grammar smoke test and fail only on parser-style errors; missing Android symbols
# are expected in this environment.
if [ "${OPENROAD_SKIP_JAVAC_SMOKE:-0}" != "1" ] && command -v javac >/dev/null 2>&1; then
  set +e
  javac -proc:none -Xmaxerrs 1000 "$ROOT"/app/src/main/java/uk/co/bengoodman/clearroute/*.java >"$ROOT/.javac-smoke.log" 2>&1
  set -e
  if grep -Eq "';' expected|illegal start|reached end of file|class, interface, enum, or record expected|not a statement|\\) expected|\\} expected" "$ROOT/.javac-smoke.log"; then
    cat "$ROOT/.javac-smoke.log"
    echo 'Java grammar smoke test failed.' >&2
    exit 1
  fi
  rm -f "$ROOT/.javac-smoke.log"
fi
