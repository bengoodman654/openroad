package uk.co.bengoodman.clearroute;

import android.content.Context;
import android.net.Uri;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ApiClient {
    public interface Callback {
        void onSuccess(String json);
        void onError(String message);
    }

    /** Small axis-aligned no-go area used for an in-navigation manual detour. */
    public static final class AvoidBox {
        public final double south, west, north, east;
        public AvoidBox(double south, double west, double north, double east) {
            this.south = Math.min(south, north);
            this.north = Math.max(south, north);
            this.west = Math.min(west, east);
            this.east = Math.max(west, east);
        }
    }

    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(3);
    private static final Object VALHALLA_LOCK = new Object();
    private static long lastValhallaRequestAt = 0L;
    private static final String VALHALLA_ROUTE_URL = "https://valhalla1.openstreetmap.de/route";

    private ApiClient() {}


    public static void search(Context context, String query, Double lat, Double lon, Callback callback) {
        search(context, query, lat, lon, false, 8, null, callback);
    }

    public static void searchSuggestions(Context context, String query, Double lat, Double lon, Callback callback) {
        search(context, query, lat, lon, true, 6, null, callback);
    }

    public static void searchMapArea(Context context, String query,
                                     double north, double west, double south, double east,
                                     Callback callback) {
        search(context, query, null, null, false, 24,
                new double[]{north, west, south, east}, callback);
    }

    private static void search(Context context, String query, Double lat, Double lon,
                               boolean typeAhead, int limit, double[] bounds, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                String key = requireKey(context);
                StringBuilder url = new StringBuilder("https://api.tomtom.com/search/2/search/")
                        .append(Uri.encode(query)).append(".json")
                        .append("?key=").append(Uri.encode(key))
                        .append("&countrySet=GB&language=en-GB")
                        .append("&idxSet=POI,PAD,Str,Xstr,Geo,Addr,EPP")
                        .append("&limit=").append(limit)
                        .append("&typeahead=").append(typeAhead ? "true" : "false");
                if (bounds != null && bounds.length == 4) {
                    double north = Math.max(bounds[0], bounds[2]);
                    double south = Math.min(bounds[0], bounds[2]);
                    double west = Math.min(bounds[1], bounds[3]);
                    double east = Math.max(bounds[1], bounds[3]);
                    String topLeft = north + "," + west;
                    String btmRight = south + "," + east;
                    url.append("&topLeft=").append(Uri.encode(topLeft));
                    url.append("&btmRight=").append(Uri.encode(btmRight));
                    url.append("&geobias=").append(Uri.encode("rectangle:" + north + "," + west + "," + south + "," + east));
                } else if (lat != null && lon != null) {
                    url.append("&lat=").append(lat).append("&lon=").append(lon);
                }
                callback.onSuccess(get(url.toString(), null, null));
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Search failed" : e.getMessage());
            }
        });
    }

    public static void route(Context context, double originLat, double originLon,
                             double destLat, double destLon, String mode, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                callback.onSuccess(routeSync(context, originLat, originLon, destLat, destLon, mode));
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Route calculation failed" : e.getMessage());
            }
        });
    }

    public static void routeVia(Context context, double originLat, double originLon,
                                double viaLat, double viaLon, double destLat, double destLon,
                                String mode, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                callback.onSuccess(routeViaSync(context, originLat, originLon, viaLat, viaLon, destLat, destLon, mode, Collections.emptyList()));
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Could not add that stop" : e.getMessage());
            }
        });
    }

    /** Ordered intermediate stops survive every reroute, not just the first. */
    public static String routeWithStopsSync(Context context, double originLat, double originLon,
                                            JSONArray stops, double destLat, double destLon,
                                            String mode, List<AvoidBox> avoidAreas) throws Exception {
        if (stops == null || stops.length() == 0)
            return routeSync(context, originLat, originLon, destLat, destLon, mode, avoidAreas);
        if (stops.length() > 6) throw new IllegalArgumentException("Too many route stops");
        if (stops.length() == 1) {
            JSONObject item = stops.getJSONObject(0);
            return routeViaSync(context, originLat, originLon,
                    item.getDouble("lat"), item.getDouble("lon"), destLat, destLon, mode, avoidAreas);
        }
        if (!"drive".equals(mode))
            throw new IllegalArgumentException("Multiple stops are currently supported for driving");
        List<double[]> via = new java.util.ArrayList<>();
        for (int i=0; i<stops.length(); i++) {
            JSONObject item = stops.getJSONObject(i);
            double lat=item.getDouble("lat"), lon=item.getDouble("lon");
            if (!Double.isFinite(lat) || !Double.isFinite(lon) || Math.abs(lat)>90 || Math.abs(lon)>180)
                throw new IllegalArgumentException("Invalid stop coordinate");
            via.add(new double[]{lat,lon});
        }
        return requestTomTomRouteWithStopsInternal(context,originLat,originLon,via,
                destLat,destLon,mode,true,0,avoidAreas);
    }

    public static void routeWithStops(Context context, double originLat, double originLon,
                                      JSONArray stops, double destLat, double destLon,
                                      String mode, Callback callback) {
        EXECUTOR.execute(() -> {
            try { callback.onSuccess(routeWithStopsSync(context,originLat,originLon,stops,destLat,destLon,mode,java.util.Collections.emptyList())); }
            catch (Exception e) { callback.onError(e.getMessage()==null?"Could not calculate the stops":e.getMessage()); }
        });
    }

    public static String routeViaSync(Context context, double originLat, double originLon,
                                      double viaLat, double viaLon, double destLat, double destLon,
                                      String mode, List<AvoidBox> avoidAreas) throws Exception {
        if ("cycle".equals(mode) || "walk".equals(mode)) {
            return requestActiveTravelRouteInternal(originLat, originLon, viaLat, viaLon, destLat, destLon, mode, 0, avoidAreas);
        }
        return requestTomTomRouteInternal(context, originLat, originLon, viaLat, viaLon, destLat, destLon, mode, true, 0, avoidAreas);
    }

    /** Search only the remaining part of the active route for useful POIs. */
    public static void searchAlongRoute(Context context, String responseJson, int routeIndex,
                                        double currentLat, double currentLon, String query,
                                        Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                String key = requireKey(context);
                RouteMath.ParsedRoute parsed = RouteMath.parse(responseJson, routeIndex);
                if (parsed.points.size() < 2) throw new Exception("The active route has no searchable geometry.");
                RouteMath.Projection projection = RouteMath.project(parsed, currentLat, currentLon);
                int start = Math.max(0, Math.min(projection.segmentIndex, parsed.points.size() - 2));

                JSONArray points = new JSONArray();
                points.put(new JSONObject().put("lat", currentLat).put("lon", currentLon));
                int remaining = parsed.points.size() - (start + 1);
                int step = Math.max(1, (int)Math.ceil(remaining / 150.0));
                for (int i = start + 1; i < parsed.points.size(); i += step) {
                    RouteMath.Point pt = parsed.points.get(i);
                    points.put(new JSONObject().put("lat", pt.lat).put("lon", pt.lon));
                }
                RouteMath.Point last = parsed.points.get(parsed.points.size() - 1);
                JSONObject lastJson = new JSONObject().put("lat", last.lat).put("lon", last.lon);
                if (points.length() < 2 || points.optJSONObject(points.length()-1) == null ||
                        Math.abs(points.optJSONObject(points.length()-1).optDouble("lat") - last.lat) > 1e-7 ||
                        Math.abs(points.optJSONObject(points.length()-1).optDouble("lon") - last.lon) > 1e-7) {
                    points.put(lastJson);
                }
                JSONObject body = new JSONObject().put("route", new JSONObject().put("points", points));
                String url = "https://api.tomtom.com/search/2/searchAlongRoute/" + Uri.encode(query) + ".json"
                        + "?key=" + Uri.encode(key)
                        + "&maxDetourTime=900&limit=12&detourOffset=true&sortBy=detourTime"
                        + "&openingHours=nextSevenDays&language=en-GB";
                callback.onSuccess(postJson(url, body.toString()));
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Along-route search failed" : e.getMessage());
            }
        });
    }

    /**
     * Routes shown to the user. Driving gets a live-traffic fastest route plus useful
     * alternatives and, when it is genuinely different, a baseline "Usual route"
     * calculated without current incidents. This makes live traffic deviations visible
     * rather than silently replacing the route a driver would normally expect.
     */
    public static void routeOptions(Context context, double originLat, double originLon,
                                    double destLat, double destLon, String mode, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                callback.onSuccess(routeOptionsSync(context, originLat, originLon, destLat, destLon, mode));
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Route calculation failed" : e.getMessage());
            }
        });
    }

    // Public-transport routing lives in TransitClient. It is intentionally not implemented
    // here so road/search APIs cannot accidentally reintroduce a mandatory TransportAPI path.

    public static String routeSync(Context context, double originLat, double originLon,
                                   double destLat, double destLon, String mode) throws Exception {
        return routeSync(context, originLat, originLon, destLat, destLon, mode, Collections.emptyList());
    }

    public static String routeSync(Context context, double originLat, double originLon,
                                   double destLat, double destLon, String mode,
                                   List<AvoidBox> avoidAreas) throws Exception {
        if ("cycle".equals(mode) || "walk".equals(mode)) {
            return requestActiveTravelRoute(originLat, originLon, destLat, destLon, mode, 0, avoidAreas);
        }
        return requestTomTomRoute(context, originLat, originLon, destLat, destLon, mode, true, 0, avoidAreas);
    }

    private static String routeOptionsSync(Context context, double originLat, double originLon,
                                           double destLat, double destLon, String mode) throws Exception {
        if (!"drive".equals(mode)) {
            return requestActiveTravelRoute(originLat, originLon, destLat, destLon, mode, 2, Collections.emptyList());
        }

        JSONObject live = new JSONObject(requestTomTomRoute(context, originLat, originLon, destLat, destLon, mode, true, 2, Collections.emptyList()));
        JSONArray liveRoutes = preferLegalTravelModeRoutes(live.optJSONArray("routes"), mode);
        if (liveRoutes == null || liveRoutes.length() == 0) return live.toString();

        JSONArray combined = new JSONArray();
        JSONObject fastestNow = liveRoutes.getJSONObject(0);
        decorateRoute(fastestNow, "Fastest now", true, mode);
        combined.put(fastestNow);

        try {
            JSONObject baseline = new JSONObject(requestTomTomRoute(context, originLat, originLon, destLat, destLon, mode, false, 0, Collections.emptyList()));
            JSONArray baselineRoutes = baseline.optJSONArray("routes");
            if (baselineRoutes != null && baselineRoutes.length() > 0) {
                JSONObject usual = baselineRoutes.getJSONObject(0);
                if (!sameRoute(fastestNow, usual)) {
                    decorateRoute(usual, "Usual route", false, mode);
                    combined.put(usual);
                }
            }
        } catch (Exception ignored) {
            // A live route is more important than failing the whole request because the
            // optional no-live-traffic comparison could not be fetched.
        }

        for (int i = 1; i < liveRoutes.length() && combined.length() < 3; i++) {
            JSONObject candidate = liveRoutes.getJSONObject(i);
            boolean duplicate = false;
            for (int j = 0; j < combined.length(); j++) {
                if (sameRoute(candidate, combined.getJSONObject(j))) { duplicate = true; break; }
            }
            if (!duplicate) {
                decorateRoute(candidate, "Alternative", true, mode);
                combined.put(candidate);
            }
        }

        try {
            android.content.SharedPreferences routePrefs = context.getSharedPreferences("clearroute_local", Context.MODE_PRIVATE);
            boolean preferMotorways = routePrefs.getBoolean("prefer_motorways", false);
            JSONObject motorway = new JSONObject(requestMotorwayHeavyRoute(originLat, originLon, destLat, destLon)).optJSONArray("routes").optJSONObject(0);
            if (motorway != null) {
                motorway.put("clearRouteLabel", "Motorway-heavy");
                motorway.put("clearRouteWarning", "Motorway preference uses OpenStreetMap routing; live traffic and speed-limit sections are not included on this option.");
                boolean duplicate = false;
                for (int j = 0; j < combined.length(); j++) if (sameRoute(motorway, combined.getJSONObject(j))) { duplicate = true; break; }
                if (!duplicate) {
                    if (preferMotorways) {
                        JSONArray ordered = new JSONArray(); ordered.put(motorway);
                        for (int j = 0; j < combined.length() && ordered.length() < 3; j++) ordered.put(combined.getJSONObject(j));
                        combined = ordered;
                    } else if (combined.length() < 3) combined.put(motorway);
                }
            }
        } catch (Exception ignored) {}

        live.put("routes", combined);
        return live.toString();
    }

    private static String requestMotorwayHeavyRoute(double originLat, double originLon, double destLat, double destLon) throws Exception {
        JSONObject body = new JSONObject();
        JSONArray locations = new JSONArray();
        locations.put(new JSONObject().put("lat", originLat).put("lon", originLon));
        locations.put(new JSONObject().put("lat", destLat).put("lon", destLon));
        body.put("locations", locations);
        body.put("costing", "auto");
        body.put("units", "kilometers");
        body.put("language", "en-GB");
        body.put("directions_type", "instructions");
        body.put("shape_format", "polyline6");
        body.put("alternates", 0);
        JSONObject auto = new JSONObject();
        auto.put("use_highways", 1.0);
        auto.put("use_tolls", 0.5);
        auto.put("use_ferry", 0.2);
        body.put("costing_options", new JSONObject().put("auto", auto));
        String raw;
        synchronized (VALHALLA_LOCK) {
            long now = System.currentTimeMillis();
            long wait = 1050L - (now - lastValhallaRequestAt);
            if (wait > 0) try { Thread.sleep(wait); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            raw = postJsonGeneric(VALHALLA_ROUTE_URL, body.toString(), "motorway-heavy routing", "X-Client-Id", "OpenRoad-personal-android");
            lastValhallaRequestAt = System.currentTimeMillis();
        }
        return convertValhallaResponse(raw, "drive");
    }

    private static String requestTomTomRoute(Context context, double originLat, double originLon,
                                       double destLat, double destLon, String mode,
                                       boolean liveTraffic, int maxAlternatives,
                                       List<AvoidBox> avoidAreas) throws Exception {
        return requestTomTomRouteInternal(context, originLat, originLon, null, null,
                destLat, destLon, mode, liveTraffic, maxAlternatives, avoidAreas);
    }

    private static String requestTomTomRouteInternal(Context context, double originLat, double originLon,
                                       Double viaLat, Double viaLon, double destLat, double destLon, String mode,
                                       boolean liveTraffic, int maxAlternatives,
                                       List<AvoidBox> avoidAreas) throws Exception {
        List<double[]> via = new java.util.ArrayList<>();
        if (viaLat != null && viaLon != null) via.add(new double[]{viaLat,viaLon});
        return requestTomTomRouteWithStopsInternal(context, originLat, originLon, via,
                destLat, destLon, mode, liveTraffic, maxAlternatives, avoidAreas);
    }

    private static String requestTomTomRouteWithStopsInternal(Context context, double originLat, double originLon,
                                          List<double[]> via, double destLat, double destLon, String mode,
                                          boolean liveTraffic, int maxAlternatives,
                                          List<AvoidBox> avoidAreas) throws Exception {
        String key = requireKey(context);
        String travelMode = "cycle".equals(mode) ? "bicycle" : ("walk".equals(mode) ? "pedestrian" : "car");
        StringBuilder url = new StringBuilder("https://api.tomtom.com/routing/1/calculateRoute/")
                .append(originLat).append(',').append(originLon).append(':');
        for(double[] point : via) url.append(point[0]).append(',').append(point[1]).append(':');
        url.append(destLat).append(',').append(destLon).append("/json")
                .append("?key=").append(Uri.encode(key))
                .append("&travelMode=").append(travelMode)
                .append("&routeType=fastest")
                .append("&traffic=").append(liveTraffic ? "true" : "false")
                .append("&maxAlternatives=").append(Math.max(0, maxAlternatives))
                .append("&routeRepresentation=polyline")
                .append("&coordinatePrecision=full")
                .append("&sectionType=importantRoadStretch")
                .append("&sectionType=travelMode")
                .append("&departAt=now");
        if ("drive".equals(mode)) {
            // A normal car route should not deliberately use HOV/carpool-only or unpaved
            // roads. Time-dependent access restrictions are evaluated for departure now.
            url.append("&avoid=carpools&avoid=unpavedRoads");
            android.content.SharedPreferences routePrefs = context.getSharedPreferences("clearroute_local", Context.MODE_PRIVATE);
            if (routePrefs.getBoolean("avoid_motorways", false)) url.append("&avoid=motorways");
            if (routePrefs.getBoolean("avoid_tolls", false)) url.append("&avoid=tollRoads");
            if (routePrefs.getBoolean("avoid_ferries", false)) url.append("&avoid=ferries");
            url.append("&sectionType=speedLimit")
                    .append("&computeTravelTimeFor=all");
        }
        url.append("&instructionsType=text")
                .append("&instructionAnnouncementPoints=all")
                .append("&language=en-GB");

        if (avoidAreas == null || avoidAreas.isEmpty()) {
            return get(url.toString(), null, null);
        }

        JSONObject body = new JSONObject();
        JSONObject avoid = new JSONObject();
        JSONArray rectangles = new JSONArray();
        int count = 0;
        for (AvoidBox box : avoidAreas) {
            if (box == null || count++ >= 10) continue;
            JSONObject rectangle = new JSONObject();
            rectangle.put("southWestCorner", new JSONObject()
                    .put("latitude", box.south).put("longitude", box.west));
            rectangle.put("northEastCorner", new JSONObject()
                    .put("latitude", box.north).put("longitude", box.east));
            rectangles.put(rectangle);
        }
        avoid.put("rectangles", rectangles);
        body.put("avoidAreas", avoid);
        return postJson(url.toString(), body.toString());
    }

    /**
     * Safety-first walking/cycling routing. Valhalla uses the OpenStreetMap graph and exposes
     * dynamic costing options that let ClearRoute prefer cycleways, footways, sidewalks and
     * living streets instead of merely asking for the fastest bicycle/pedestrian route.
     *
     * The FOSSGIS public Valhalla service is used only by this one-user personal build. We
     * identify the client and throttle requests to respect its published fair-use limit.
     */
    private static String requestActiveTravelRoute(double originLat, double originLon,
                                                   double destLat, double destLon, String mode,
                                                   int alternates, List<AvoidBox> avoidAreas) throws Exception {
        return requestActiveTravelRouteInternal(originLat, originLon, null, null, destLat, destLon, mode, alternates, avoidAreas);
    }

    private static String requestActiveTravelRouteInternal(double originLat, double originLon,
                                                   Double viaLat, Double viaLon,
                                                   double destLat, double destLon, String mode,
                                                   int alternates, List<AvoidBox> avoidAreas) throws Exception {
        // The public Valhalla server hard-limits one pedestrian request to 100 km.
        // Intercity walking must be checked as multiple real, contiguous foot paths,
        // not rejected or shown as a straight line.
        if ("walk".equals(mode) && (distanceMetres(originLat,originLon,destLat,destLon)>80000.0 ||
             (viaLat!=null && viaLon!=null &&
                (distanceMetres(originLat,originLon,viaLat,viaLon)>80000.0 ||
                 distanceMetres(viaLat,viaLon,destLat,destLon)>80000.0)))) {
            if(viaLat!=null && viaLon!=null){
                JSONObject first=new JSONObject(requestActiveTravelRouteInternal(originLat,originLon,null,null,
                    viaLat,viaLon,"walk",0,avoidAreas));
                JSONObject second=new JSONObject(requestActiveTravelRouteInternal(viaLat,viaLon,null,null,
                    destLat,destLon,"walk",0,avoidAreas));
                java.util.ArrayList<JSONObject> parts=new java.util.ArrayList<>();
                parts.add(first.optJSONArray("routes").getJSONObject(0));
                parts.add(second.optJSONArray("routes").getJSONObject(0));
                return mergeVerifiedWalkingParts(parts).toString();
            }
            return requestSegmentedWalkingRoute(originLat,originLon,destLat,destLon,avoidAreas);
        }
        JSONObject body = new JSONObject();
        JSONArray locations = new JSONArray();
        locations.put(new JSONObject().put("lat", originLat).put("lon", originLon));
        if (viaLat != null && viaLon != null) locations.put(new JSONObject().put("lat", viaLat).put("lon", viaLon));
        locations.put(new JSONObject().put("lat", destLat).put("lon", destLon));
        body.put("locations", locations);
        body.put("costing", "cycle".equals(mode) ? "bicycle" : "pedestrian");
        body.put("units", "kilometers");
        body.put("language", "en-GB");
        body.put("directions_type", "instructions");
        body.put("shape_format", "polyline6");
        body.put("alternates", Math.max(0, Math.min(2, alternates)));
        body.put("date_time", new JSONObject().put("type", 0));

        JSONObject costingOptions = new JSONObject();
        if ("cycle".equals(mode)) {
            // Deliberately safety/comfort biased rather than fastest-time biased. A near-zero
            // use_roads factor strongly penalises ordinary roads when cycleways/paths exist.
            JSONObject bicycle = new JSONObject();
            bicycle.put("bicycle_type", "Hybrid");
            bicycle.put("use_roads", 0.05);
            bicycle.put("use_hills", 0.35);
            bicycle.put("avoid_bad_surfaces", 0.75);
            bicycle.put("use_living_streets", 0.9);
            bicycle.put("use_tracks", 0.45);
            bicycle.put("maneuver_penalty", 8);
            costingOptions.put("bicycle", bicycle);
        } else {
            // Factors below 1 favour dedicated pedestrian infrastructure. This makes a
            // slightly longer footway/sidewalk route cheaper than a direct road-heavy route.
            JSONObject pedestrian = new JSONObject();
            pedestrian.put("walkway_factor", 0.55);
            pedestrian.put("sidewalk_factor", 0.72);
            pedestrian.put("alley_factor", 2.5);
            pedestrian.put("driveway_factor", 5.0);
            pedestrian.put("service_factor", 1.6);
            pedestrian.put("use_living_streets", 0.9);
            pedestrian.put("use_hills", 0.5);
            pedestrian.put("max_hiking_difficulty", 0);
            pedestrian.put("maneuver_penalty", 4);
            costingOptions.put("pedestrian", pedestrian);
        }
        body.put("costing_options", costingOptions);

        // Manual "avoid road ahead" reroutes are provider-agnostic. For Valhalla, map the
        // centre of each tiny avoid box to an avoid_location so the nearby edge is excluded.
        if (avoidAreas != null && !avoidAreas.isEmpty()) {
            JSONArray avoidLocations = new JSONArray();
            int count = 0;
            for (AvoidBox box : avoidAreas) {
                if (box == null || count++ >= 10) continue;
                avoidLocations.put(new JSONObject()
                        .put("lat", (box.south + box.north) / 2.0)
                        .put("lon", (box.west + box.east) / 2.0));
            }
            if (avoidLocations.length() > 0) body.put("avoid_locations", avoidLocations);
        }

        String raw;
        synchronized (VALHALLA_LOCK) {
            long now = System.currentTimeMillis();
            long wait = 1050L - (now - lastValhallaRequestAt);
            if (wait > 0) {
                try { Thread.sleep(wait); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            }
            raw = postJsonGeneric(VALHALLA_ROUTE_URL, body.toString(), "active-travel routing",
                    "X-Client-Id", "OpenRoad-personal-android");
            lastValhallaRequestAt = System.currentTimeMillis();
        }
        return convertValhallaResponse(raw, mode);
    }


    /**
     * The public walking service rejects paths longer than 100 km (Valhalla 154).
     * Use an actual cycle-network route ONLY to select intermediate pedestrian
     * query anchors. It is NEVER rendered as the walking route; every displayed
     * metre is supplied by the pedestrian router, or the result fails closed.
     */
    private static String requestSegmentedWalkingRoute(double startLat,double startLon,
            double endLat,double endLon,List<AvoidBox> avoidAreas) throws Exception {
        double direct=distanceMetres(startLat,startLon,endLat,endLon);
        if(direct>310000)throw new Exception("This walk is too long for the public footpath service. Try a shorter section.");
        JSONObject cycle;
        try{
            cycle=new JSONObject(requestActiveTravelRouteInternal(startLat,startLon,null,null,endLat,endLon,
                    "cycle",0,avoidAreas));
        }catch(Exception e){
            throw new Exception("Long-distance walking directions need a verified route through intermediate places. The route guide is unavailable.");
        }
        JSONArray seed=cycle.optJSONArray("routes");
        JSONObject seedRoute=seed==null?null:seed.optJSONObject(0);
        java.util.ArrayList<double[]> spine=routePoints(seedRoute);
        if(spine.size()<3)throw new Exception("No reliable intermediate footpath locations were found for this walk.");
        double[] cumulative=new double[spine.size()];
        for(int i=1;i<spine.size();i++)
            cumulative[i]=cumulative[i-1]+distanceMetres(spine.get(i-1)[0],spine.get(i-1)[1],
                                                           spine.get(i)[0],spine.get(i)[1]);
        double length=cumulative[cumulative.length-1];
        int count=Math.max(2,(int)Math.ceil(length/38000.0));
        if(count>9)throw new Exception("This walking route is too long for safe segmented pedestrian routing.");
        java.util.ArrayList<double[]> anchors=new java.util.ArrayList<>();
        anchors.add(new double[]{startLat,startLon});
        int cursor=1;
        for(int i=1;i<count;i++){
            double target=length*i/count;
            while(cursor<spine.size()-1 && cumulative[cursor]<target)cursor++;
            double[] here=spine.get(Math.min(cursor,spine.size()-2));
            if(distanceMetres(anchors.get(anchors.size()-1)[0],anchors.get(anchors.size()-1)[1],
                    here[0],here[1])>300.0)anchors.add(here);
        }
        anchors.add(new double[]{endLat,endLon});
        if(anchors.size()>10)throw new Exception("Too many pedestrian sections for one route.");
        java.util.ArrayList<JSONObject> walked=new java.util.ArrayList<>();
        for(int i=1;i<anchors.size();i++){
            if(Thread.currentThread().isInterrupted())throw new java.io.InterruptedIOException("Walking search cancelled");
            double[] a=anchors.get(i-1),b=anchors.get(i);
            JSONObject piece;
            try{
                piece=new JSONObject(requestActiveTravelRouteInternal(a[0],a[1],null,null,b[0],b[1],
                        "walk",0,avoidAreas));
            }catch(Exception e){
                throw new Exception("Could not verify a continuous walking path through all intermediate places. Try shorter sections.");
            }
            JSONArray routes=piece.optJSONArray("routes");
            JSONObject segment=routes==null?null:routes.optJSONObject(0);
            java.util.ArrayList<double[]> points=routePoints(segment);
            if(points.size()<2 ||
                 distanceMetres(points.get(0)[0],points.get(0)[1],a[0],a[1])>700 ||
                 distanceMetres(points.get(points.size()-1)[0],points.get(points.size()-1)[1],b[0],b[1])>700)
                throw new Exception("Walking route has a disconnected section; refusing to show an inaccurate path.");
            walked.add(segment);
        }
        return mergeVerifiedWalkingParts(walked).toString();
    }

    private static JSONObject mergeVerifiedWalkingParts(java.util.List<JSONObject> parts) throws Exception {
        if(parts==null||parts.isEmpty())throw new Exception("No verified walking sections");
        JSONArray legs=new JSONArray(),instructions=new JSONArray();
        long length=0,time=0;
        long previousTotalPoints=0;
        for(JSONObject part:parts){
            if(part==null)throw new Exception("Missing pedestrian segment");
            JSONObject summary=part.optJSONObject("summary");
            JSONArray sectionLegs=part.optJSONArray("legs");
            if(summary==null||sectionLegs==null||sectionLegs.length()==0)
                throw new Exception("Incomplete pedestrian route");
            long segmentMetres=summary.optLong("lengthInMeters",0);
            long segmentSeconds=summary.optLong("travelTimeInSeconds",0);
            if(segmentMetres<50||segmentMetres>100000||segmentSeconds<=0)
                throw new Exception("Pedestrian segment exceeded the service limit");
            long legPointCount=0;
            for(int j=0;j<sectionLegs.length();j++){
                JSONObject leg=sectionLegs.optJSONObject(j);
                if(leg==null||leg.optJSONArray("points")==null)throw new Exception("Invalid pedestrian geometry");
                legPointCount+=leg.optJSONArray("points").length();
                legs.put(leg);
            }
            JSONArray commands=part.optJSONObject("guidance")==null?null:
                    part.optJSONObject("guidance").optJSONArray("instructions");
            if(commands!=null){
                for(int j=0;j<commands.length();j++){
                    JSONObject row=commands.optJSONObject(j);
                    if(row==null)continue;
                    JSONObject copy=new JSONObject(row.toString());
                    copy.put("pointIndex",Math.max(0,previousTotalPoints+row.optLong("pointIndex",0)));
                    copy.put("routeOffsetInMeters",length+row.optDouble("routeOffsetInMeters",0));
                    copy.put("travelTimeInSeconds",time+row.optLong("travelTimeInSeconds",0));
                    instructions.put(copy);
                }
            }
            previousTotalPoints+=legPointCount;
            length+=segmentMetres;
            time+=segmentSeconds;
        }
        JSONObject route=new JSONObject()
          .put("summary",new JSONObject().put("lengthInMeters",length).put("travelTimeInSeconds",time))
          .put("legs",legs).put("guidance",new JSONObject().put("instructions",instructions))
          .put("clearRouteProvider","Valhalla / OpenStreetMap pedestrian segments")
          .put("clearRouteLabel","Verified walking route")
          .put("clearRouteWalkSegments",parts.size())
          .put("clearRouteLiveTraffic",false);
        return new JSONObject().put("routes",new JSONArray().put(route));
    }

    private static String convertValhallaResponse(String raw, String mode) throws Exception {
        JSONObject source = new JSONObject(raw);
        JSONObject output = new JSONObject();
        JSONArray routes = new JSONArray();
        JSONObject primaryTrip = source.optJSONObject("trip");
        if (primaryTrip == null) throw new Exception("The active-travel router returned no route.");
        routes.put(convertValhallaTrip(primaryTrip, mode, true));
        JSONArray alternates = source.optJSONArray("alternates");
        if (alternates != null) {
            for (int i = 0; i < alternates.length() && routes.length() < 3; i++) {
                JSONObject wrapper = alternates.optJSONObject(i);
                JSONObject trip = wrapper == null ? null : wrapper.optJSONObject("trip");
                if (trip != null) routes.put(convertValhallaTrip(trip, mode, false));
            }
        }
        output.put("routes", routes);
        return output.toString();
    }

    private static JSONObject convertValhallaTrip(JSONObject trip, String mode, boolean primary) throws Exception {
        JSONObject route = new JSONObject();
        JSONObject tripSummary = trip.optJSONObject("summary");
        JSONObject summary = new JSONObject();
        summary.put("lengthInMeters", tripSummary == null ? 0 : Math.round(tripSummary.optDouble("length", 0) * 1000.0));
        summary.put("travelTimeInSeconds", tripSummary == null ? 0 : Math.round(tripSummary.optDouble("time", 0)));
        route.put("summary", summary);
        route.put("clearRouteLabel", primary ? "Paths preferred" : ("cycle".equals(mode) ? "Cycle alternative" : "Walking alternative"));
        route.put("clearRouteLiveTraffic", false);
        route.put("clearRouteProvider", "Valhalla / OpenStreetMap");

        JSONArray outputLegs = new JSONArray();
        JSONArray guidanceInstructions = new JSONArray();
        ArrayList<double[]> allPoints = new ArrayList<>();
        JSONArray legs = trip.optJSONArray("legs");
        long elapsedSeconds = 0L;
        double routeOffset = 0.0;
        int globalPointBase = 0;
        if (legs != null) {
            for (int li = 0; li < legs.length(); li++) {
                JSONObject leg = legs.optJSONObject(li);
                if (leg == null) continue;
                ArrayList<double[]> points = decodePolyline6(leg.optString("shape", ""));
                JSONArray pointJson = new JSONArray();
                int skip = (!allPoints.isEmpty() && !points.isEmpty() && samePoint(allPoints.get(allPoints.size()-1), points.get(0))) ? 1 : 0;
                for (int i = skip; i < points.size(); i++) {
                    double[] p = points.get(i);
                    allPoints.add(p);
                    pointJson.put(new JSONObject().put("latitude", p[0]).put("longitude", p[1]));
                }
                JSONObject outLeg = new JSONObject();
                outLeg.put("points", pointJson);
                outputLegs.put(outLeg);

                // Build a cumulative distance table for this leg so Valhalla maneuver shape
                // indexes become the route offsets expected by ClearRoute's navigator.
                double[] legCum = new double[points.size()];
                for (int i = 1; i < points.size(); i++) {
                    legCum[i] = legCum[i-1] + distanceMetres(points.get(i-1)[0], points.get(i-1)[1], points.get(i)[0], points.get(i)[1]);
                }
                JSONArray maneuvers = leg.optJSONArray("maneuvers");
                if (maneuvers != null) {
                    for (int mi = 0; mi < maneuvers.length(); mi++) {
                        JSONObject m = maneuvers.optJSONObject(mi);
                        if (m == null) continue;
                        int localIndex = Math.max(0, Math.min(m.optInt("begin_shape_index", 0), Math.max(0, points.size()-1)));
                        int pointIndex = Math.max(0, globalPointBase + localIndex - skip);
                        JSONObject ins = new JSONObject();
                        ins.put("pointIndex", pointIndex);
                        ins.put("routeOffsetInMeters", routeOffset + (legCum.length == 0 ? 0 : legCum[localIndex]));
                        ins.put("travelTimeInSeconds", elapsedSeconds);
                        ins.put("message", m.optString("instruction", "Continue"));
                        ins.put("maneuver", valhallaManeuver(m.optInt("type", 0)));
                        ins.put("instructionType", "TURN");
                        guidanceInstructions.put(ins);
                        elapsedSeconds += Math.max(0, Math.round(m.optDouble("time", 0)));
                    }
                }
                if (legCum.length > 0) routeOffset += legCum[legCum.length - 1];
                globalPointBase = allPoints.size();
            }
        }
        route.put("legs", outputLegs);
        route.put("guidance", new JSONObject().put("instructions", guidanceInstructions));
        return route;
    }

    private static boolean samePoint(double[] a, double[] b) {
        return a != null && b != null && Math.abs(a[0]-b[0]) < 1e-7 && Math.abs(a[1]-b[1]) < 1e-7;
    }

    private static ArrayList<double[]> decodePolyline6(String encoded) throws Exception {
        ArrayList<double[]> out = new ArrayList<>();
        if (encoded == null || encoded.isEmpty()) return out;
        int index = 0, lat = 0, lon = 0;
        while (index < encoded.length()) {
            int[] a = decodePolylineValue(encoded, index); index = a[1]; lat += a[0];
            int[] b = decodePolylineValue(encoded, index); index = b[1]; lon += b[0];
            out.add(new double[]{lat / 1_000_000.0, lon / 1_000_000.0});
        }
        return out;
    }

    private static int[] decodePolylineValue(String encoded, int index) throws Exception {
        int result = 0, shift = 0, value;
        do {
            if (index >= encoded.length()) throw new Exception("Invalid active-travel route geometry");
            value = encoded.charAt(index++) - 63;
            result |= (value & 0x1f) << shift;
            shift += 5;
        } while (value >= 0x20);
        int delta = ((result & 1) != 0) ? ~(result >> 1) : (result >> 1);
        return new int[]{delta, index};
    }

    private static String valhallaManeuver(int type) {
        switch (type) {
            case 2: case 9: case 10: case 11: case 18: case 20: return "TURN_RIGHT";
            case 3: case 14: case 15: case 16: case 19: case 21: return "TURN_LEFT";
            case 12: return "UTURN_RIGHT";
            case 13: return "UTURN_LEFT";
            case 23: return "KEEP_RIGHT";
            case 24: return "KEEP_LEFT";
            case 26: case 27: return "ROUNDABOUT";
            case 25: return "MERGE";
            default: return "STRAIGHT";
        }
    }

    private static JSONArray preferLegalTravelModeRoutes(JSONArray routes, String mode) {
        if (routes == null || routes.length() < 2) return routes;
        JSONArray legal = new JSONArray();
        for (int i = 0; i < routes.length(); i++) {
            JSONObject route = routes.optJSONObject(i);
            if (route != null && !hasTravelModeViolation(route, mode)) legal.put(route);
        }
        return legal.length() > 0 ? legal : routes;
    }

    private static boolean hasTravelModeViolation(JSONObject route, String mode) {
        String expected = "cycle".equals(mode) ? "bicycle" : ("walk".equals(mode) ? "pedestrian" : "car");
        JSONArray sections = route == null ? null : route.optJSONArray("sections");
        if (sections == null) return false;
        for (int i = 0; i < sections.length(); i++) {
            JSONObject section = sections.optJSONObject(i);
            if (section == null || !"TRAVEL_MODE".equals(section.optString("sectionType"))) continue;
            String actual = section.optString("travelMode", expected);
            if ("other".equalsIgnoreCase(actual)) return true;
        }
        return false;
    }

    private static void decorateRoute(JSONObject route, String label, boolean liveTraffic, String mode) {
        try {
            route.put("clearRouteLabel", label);
            route.put("clearRouteLiveTraffic", liveTraffic);
            boolean restricted = hasTravelModeViolation(route, mode);
            route.put("clearRouteRestricted", restricted);
            if (restricted) route.put("clearRouteWarning", "This route contains a section TomTom cannot confirm for this travel mode.");
            String via = importantRoads(route);
            if (!via.isEmpty()) route.put("clearRouteVia", via);
        } catch (Exception ignored) {}
    }

    private static String importantRoads(JSONObject route) {
        JSONArray sections = route.optJSONArray("sections");
        if (sections == null) return "";
        java.util.TreeMap<Integer, String> byImportance = new java.util.TreeMap<>();
        for (int i = 0; i < sections.length(); i++) {
            JSONObject section = sections.optJSONObject(i);
            if (section == null || !"IMPORTANT_ROAD_STRETCH".equals(section.optString("sectionType"))) continue;
            int importance = section.optInt("importantRoadStretchIndex", 9999);
            String road = "";
            JSONArray nums = section.optJSONArray("roadNumbers");
            if (nums != null && nums.length() > 0) road = nums.optJSONObject(0) == null ? "" : nums.optJSONObject(0).optString("text", "");
            if (road.isEmpty()) {
                JSONObject street = section.optJSONObject("streetName");
                if (street != null) road = street.optString("text", "");
            }
            if (!road.isEmpty() && !byImportance.containsValue(road)) byImportance.put(importance, road);
        }
        StringBuilder out = new StringBuilder();
        int count = 0;
        for (String road : byImportance.values()) {
            if (count++ >= 3) break;
            if (out.length() > 0) out.append(" · ");
            out.append(road);
        }
        return out.toString();
    }

    private static boolean sameRoute(JSONObject a, JSONObject b) {
        try {
            JSONObject sa = a.optJSONObject("summary"), sb = b.optJSONObject("summary");
            double la = sa == null ? 0 : sa.optDouble("lengthInMeters", 0);
            double lb = sb == null ? 0 : sb.optDouble("lengthInMeters", 0);
            if (la > 0 && lb > 0 && Math.abs(la - lb) / Math.max(la, lb) > 0.035) return false;

            java.util.ArrayList<double[]> pa = routePoints(a);
            java.util.ArrayList<double[]> pb = routePoints(b);
            if (pa.size() < 4 || pb.size() < 4) return la > 0 && lb > 0 && Math.abs(la-lb) / Math.max(la,lb) < 0.015;
            double[] fractions = {0.25, 0.5, 0.75};
            for (double f : fractions) {
                double[] xa = pa.get(Math.min(pa.size()-1, (int)Math.round((pa.size()-1)*f)));
                double[] xb = pb.get(Math.min(pb.size()-1, (int)Math.round((pb.size()-1)*f)));
                if (distanceMetres(xa[0], xa[1], xb[0], xb[1]) > 1800) return false;
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private static java.util.ArrayList<double[]> routePoints(JSONObject route) {
        java.util.ArrayList<double[]> out = new java.util.ArrayList<>();
        JSONArray legs = route.optJSONArray("legs");
        if (legs == null) return out;
        for (int i = 0; i < legs.length(); i++) {
            JSONObject leg = legs.optJSONObject(i);
            JSONArray points = leg == null ? null : leg.optJSONArray("points");
            if (points == null) continue;
            for (int j = 0; j < points.length(); j++) {
                JSONObject p = points.optJSONObject(j);
                if (p != null) out.add(new double[]{p.optDouble("latitude"), p.optDouble("longitude")});
            }
        }
        return out;
    }

    private static double distanceMetres(double lat1, double lon1, double lat2, double lon2) {
        double r = 6371000.0;
        double p1 = Math.toRadians(lat1), p2 = Math.toRadians(lat2);
        double dp = Math.toRadians(lat2-lat1), dl = Math.toRadians(lon2-lon1);
        double h = Math.sin(dp/2)*Math.sin(dp/2) + Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);
        return 2*r*Math.atan2(Math.sqrt(h), Math.sqrt(1-h));
    }

    public static String incidents(Context context, double west, double south, double east, double north) throws Exception {
        String key = requireKey(context);
        String url = "https://api.tomtom.com/maps/orbis/traffic/incidents/details?apiVersion=2&bbox="
                + west + "," + south + "," + east + "," + north + "&timeValidity=present";
        return get(url, "TomTom-Api-Key", key,
                "Attributes", "incidents(type,geometry(type,coordinates),properties(iconCategory,magnitudeOfDelay,lengthInMeters,delayInSeconds,events(description)))",
                "Accept-Language", "en-GB");
    }

    private static String postJson(String urlString, String body) throws Exception {
        return postJsonGeneric(urlString, body, "TomTom");
    }

    private static String postJsonGeneric(String urlString, String body, String serviceName, String... headers) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(urlString).openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(20000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Accept", "application/json,*/*");
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("User-Agent", "OpenRoad/0.6.42 personal-android-app");
        if (headers != null) {
            for (int i = 0; i + 1 < headers.length; i += 2) {
                if (headers[i] != null && headers[i + 1] != null) connection.setRequestProperty(headers[i], headers[i + 1]);
            }
        }
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(bytes.length);
        try (OutputStream out = connection.getOutputStream()) { out.write(bytes); }
        int code = connection.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        String response = readAll(in);
        connection.disconnect();
        if (code < 200 || code >= 300) {
            if ("TomTom".equals(serviceName) && (code == 401 || code == 403)) throw new Exception("TomTom rejected the API key. Check the key in OpenRoad Settings.");
            if (code == 429) throw new Exception("The " + serviceName + " service is busy. Try again in a moment.");
            if (code >= 500) throw new Exception("The " + serviceName + " service is temporarily unavailable. Try again shortly.");
            throw new Exception("The " + serviceName + " service returned HTTP " + code + ".");
        }
        return response;
    }

    private static String requireKey(Context context) throws Exception {
        String key = SecureStore.getApiKey(context);
        if (key == null || key.trim().isEmpty()) throw new Exception("TomTom API key is not configured");
        return key.trim();
    }

    private static String get(String urlString, String... headers) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(urlString).openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(18000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("Accept", "application/json,*/*");
        connection.setRequestProperty("User-Agent", "OpenRoad/0.6.42 personal-android-app");
        if (headers != null) {
            for (int i = 0; i + 1 < headers.length; i += 2) {
                if (headers[i] != null && headers[i + 1] != null) connection.setRequestProperty(headers[i], headers[i + 1]);
            }
        }
        int code = connection.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        String body = readAll(in);
        connection.disconnect();
        if (code < 200 || code >= 300) {
            if (code == 401 || code == 403) throw new Exception("TomTom rejected the API key. Check the key in OpenRoad Settings.");
            if (code == 429) throw new Exception("TomTom request limit reached. Try again later.");
            if (code >= 500) throw new Exception("The map service is temporarily unavailable. Try again shortly.");
            throw new Exception("The navigation service returned HTTP " + code + ".");
        }
        return body;
    }

    private static String readAll(InputStream input) throws Exception {
        if (input == null) return "";
        StringBuilder out = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) out.append(line).append('\n');
        }
        return out.toString();
    }
}
