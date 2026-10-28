# OpenRoad PT v2: cancellation and response integration gate

**Research only. No Android or PHP production deployment.** Prepared 28 October 2026.
Base source archives examined read-only on isolated GitHub Actions:
Android v0.6.31 and transport server v0.2.5.

## Exact existing integration points

Android web UI, app/src/main/assets/app.js:
calculateRoute, cancelActiveRouteRequest, acceptSearchResult,
armTransitSearchWatchdog, finishRouteCalculationUi, renderTransitPlanner,
startTransitNavigation, stopTransitNavigation and doSearch.

Java, app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java:
beginRouteWork, cancelRouteWork, routeWorkCancelled, route, routeOnce,
routeWithStops and completeSearch.

Server entry point: public/api/v1/journeys.php.
PHP routing: private/lib/router.php:
openroad_plan_bus, or_route_check_budget and or_route_deadline.

These method names were confirmed from the actual archived sources; the
Python pilot is a reference, not an Android/PHP patch.

## Executable off-host contract

- pilot/request_lifecycle.py implements bounded tickets, cooperative
  cancellation states, pre-registration tombstones, ownership checks,
  client generation fencing, concurrency limits and shared fetch isolation.
- pilot/journey_options.py checks cancellation before and throughout a
  timetable search, including walking-transfer closure.
- pilot/pedestrian_graph.py checks cancellation while evaluating graph paths
  and independently checked stop links. Cancellation raises SearchCancelled,
  never a false no-route result.
- pilot/response_envelope.py never publishes a cancelled, unacknowledged,
  malformed or impossible bus itinerary as an OK result. It validates bus
  trips against continuous dated GTFS source connections, and indexes only
  returned trips, with a maximum of three alternatives. Research results
  remain NON-SELECTABLE pending real release evidence.

## Android integration requirements still to implement

1. Left Back arrow and top-right X INSIDE the Where to? input remain visible
   throughout the transport flow.
2. X during an active search invalidates the generation, stops its local
   work, requests an idempotent remote cancellation and keeps any existing
   navigation guidance. Do not silently stop guidance.
3. Back pops one screen and cancels only owned child lookups. Stopping
   guidance is a distinct, confirmed action.
4. Every new search gets a strictly newer generation. Stale callbacks,
   asynchronous map paths and later alternatives cannot reset camera,
   switch selected itineraries or resurrect old searches.
5. Cancellation, no journey and unavailable timetable coverage are
   distinct outcomes. Valid scheduled bus results do not depend on live
   vehicle updates.
6. Unverified stop access, incomplete walking geometry and unsupported
   rail legs must never be advertised as ready for navigation.

## PHP integration requirements still to implement

1. Authenticate task ownership independently of a caller-provided session
   ID. Issue cryptographically authenticated, short-lived, snapshot-bound
   task tickets on the server.
2. Store cancel-before-registration tombstones atomically across PHP-FPM
   workers. Never let late registration resurrect a cancelled task.
3. Distinguish STOPPING from STOPPED: a client abort or an HTTP error does
   not prove a PHP worker finished. Shared fetches/cache builders must not
   be terminated when one subscriber cancels.
4. Bound request size, CPU/RAM/time budgets, queue depth, lock contention
   and retained records. Use prebuilt verified snapshots; never import
   regional BODS or OSM archives during an interactive route request.
5. Return explicit capability, date, source, task, generation, outcome and
   cancellation information. Fail closed on missing or malformed identity.
6. Preserve v1 endpoints and hosting configuration until separate security,
   resource and integration acceptance can be demonstrated.

## Evidence and release boundary

Synthetic Python fixtures are exercised by the PT v2 pilot workflow. Independent
source-pinned real Bristol/Coventry BODS and OSM audit evidence is in
pilot/real-stop-crosswalk-evidence-2026-10-27.json.

Existing cancellation methods have been found in Android v0.6.31, but they
have not been integrated with this new v2 server-side contract, and actual
server process teardown has not been proved.

**All 105 production acceptance cases remain unpassed.** No live server,
installed Android app, production branch, deployment credentials, website,
mail process, cron process or updater has been altered.

## Next bounded integration steps

A. Adapt v0.6.31 Java and JS work cancellation and generations to a versioned,
   non-production v2 adapter, without changing the released v1 API.
B. Test the Where to? X and persistent Back controls with an isolated mock
   server, including stopped guidance, supersession, network loss and retry.
C. Implement and independently attack-test atomic authenticated PHP-FPM
   task tombstones, lease expiry and accurate STOPPING/STOPPED statuses.
D. Run off-host load, memory, concurrent request and fallback checks before
   any separately approved read-only host benchmarking.
E. Close verified pedestrian stop-access, UK rail licence and graph,
   full source coverage, and full acceptance gaps before any installable release.
