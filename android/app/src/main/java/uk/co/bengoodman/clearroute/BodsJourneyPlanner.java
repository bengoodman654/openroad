package uk.co.bengoodman.clearroute;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Lightweight, on-device journey planner over the official DfT/BODS GTFS timetable feed.
 *
 * This deliberately starts with the most useful reliable subset outside London: local buses in
 * England, including direct journeys and one same-stop interchange. It never needs TransportAPI.
 * The resulting scheduled itinerary can then be enriched with BODS live vehicle positions by
 * TransitClient. Walking access/egress is estimated as a straight-line distance; OpenRoad labels
 * the timetable data as scheduled and does not pretend those walking estimates are turn-by-turn
 * pedestrian routing.
 */
public final class BodsJourneyPlanner {
    private static final long MAX_AGE_MS = 24L * 60L * 60L * 1000L;
    private static final String BASE = "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/";
    private static final ZoneId LONDON = ZoneId.of("Europe/London");
    private static final int SEARCH_HORIZON_SEC = 6 * 3600;
    private static final int MAX_FIRST_TRIPS = 180;
    private static final int MAX_SECOND_TRIPS = 320;
    private static final Object REGION_FILE_LOCK = new Object();
    private static final Object META_CACHE_LOCK = new Object();
    private static volatile String cachedMetaFileKey = "";
    private static volatile LocalDate cachedTripDate = null;
    private static volatile Map<String, Stop> cachedStops = null;
    private static volatile Map<String, RouteMeta> cachedRoutes = null;
    private static volatile Map<String, TripMeta> cachedTrips = null;

    private BodsJourneyPlanner() {}

    /** Foreground searches must not block on BODS downloads or regional refreshes. */
    public static boolean hasPreparedRegion(Context context, double originLat, double originLon,
                                             double destLat, double destLon) {
        String a = regionFor(originLat, originLon), b = regionFor(destLat, destLon);
        String region = a.equals(b) ? a : commonRegion(a, b);
        if (region == null || "scotland".equals(region) || "wales".equals(region)) return false;
        File zip = new File(context.getCacheDir(), "transit/bods-gtfs/" + region + ".zip");
        // A cached ZIP is NOT a ready timetable. Only use foreground fallback if preloading
        // finished parsing the region into memory. Avoid waiting on META_CACHE_LOCK here.
        return zip.isFile() && zip.length() > 1024 &&
                System.currentTimeMillis() - zip.lastModified() < MAX_AGE_MS &&
                metaFileKey(zip).equals(cachedMetaFileKey) &&
                cachedStops != null && cachedRoutes != null && cachedTrips != null &&
                LocalDate.now(LONDON).equals(cachedTripDate);
    }

    /** Warm the regional timetable only after the user explicitly selects Public transport. */
    public static void prepare(Context context, double lat, double lon) throws Exception {
        String region = regionFor(lat, lon);
        if ("scotland".equals(region) || "wales".equals(region)) return;
        File zip = ensureRegion(context, region);
        loadStopsCached(zip);
        loadRoutesCached(zip);
        loadActiveTripsCached(zip, LocalDate.now(LONDON));
    }

    public static JSONObject plan(Context context,
                                  double originLat, double originLon,
                                  double destLat, double destLon,
                                  JSONObject settings) throws Exception {
        if (!modeEnabled(settings, "bus")) {
            throw new Exception("Bus is disabled in Public transport settings. OpenRoad's local official-data planner currently uses BODS bus timetables outside London.");
        }

        String originRegion = regionFor(originLat, originLon);
        String destinationRegion = regionFor(destLat, destLon);
        String region = originRegion.equals(destinationRegion) ? originRegion : commonRegion(originRegion, destinationRegion);
        if (region == null) {
            throw new Exception("This journey crosses an area not yet covered by OpenRoad's local BODS bus planner.");
        }
        if ("scotland".equals(region) || "wales".equals(region)) {
            throw new Exception("OpenRoad's local BODS journey planner currently covers bus services in England outside London. Scotland and Wales need their regional timetable routing layer before OpenRoad can plan this journey without a fallback service.");
        }

        File zip = ensureRegion(context, region);
        double walkSpeed = walkSpeed(settings);
        // Walking is no longer a user-facing hard filter. Use a generous internal candidate
        // radius so useful journeys are considered, then let Quickest / Fewest changes /
        // Balanced ranking decide which three are shown.
        double stopRadius = 4000.0;
        int transferBuffer = transferBuffer(settings);
        int now = LocalTime.now(LONDON).toSecondOfDay();
        LocalDate today = LocalDate.now(LONDON);

        Map<String, Stop> stops = loadStopsCached(zip);
        if (stops.isEmpty()) throw new Exception("The BODS timetable did not contain usable stops.");
        Map<String, Integer> originWalk = nearbyStops(stops, originLat, originLon, stopRadius, walkSpeed, 40);
        Map<String, Integer> destinationWalk = nearbyStops(stops, destLat, destLon, stopRadius, walkSpeed, 40);
        if (originWalk.isEmpty()) throw new Exception("No BODS bus stop was found near the start point.");
        if (destinationWalk.isEmpty()) throw new Exception("No BODS bus stop was found near the destination.");

        Map<String, TripMeta> trips = loadActiveTripsCached(zip, today);
        if (trips.isEmpty()) throw new Exception("No scheduled BODS bus services are active today in this timetable area.");
        Map<String, RouteMeta> routes = loadRoutesCached(zip);

        // Pass 1: find boardable trips from nearby origin stops.
        Map<String, Board> firstBoards = new HashMap<>();
        try (BufferedReader reader = entryReader(zip, "stop_times.txt")) {
            if (reader == null) throw new Exception("BODS timetable is missing stop_times.txt");
            List<String> header = csv(reader.readLine());
            int tripId = indexOf(header, "trip_id"), stopId = indexOf(header, "stop_id"), seq = indexOf(header, "stop_sequence"), dep = indexOf(header, "departure_time");
            String row; int scanned = 0;
            while ((row = reader.readLine()) != null) {
                if (((++scanned) & 2047) == 0 && Thread.currentThread().isInterrupted())
                    throw new InterruptedException("Route search cancelled");
                List<String> c = csv(row);
                String trip = value(c, tripId);
                if (!trips.containsKey(trip)) continue;
                String stop = value(c, stopId);
                Integer walk = originWalk.get(stop);
                if (walk == null) continue;
                int depSec = gtfsSeconds(value(c, dep));
                if (depSec < 0) continue;
                int ready = now + walk;
                if (depSec < ready || depSec > now + SEARCH_HORIZON_SEC) continue;
                int sequence = parseInt(value(c, seq), -1);
                Board old = firstBoards.get(trip);
                Board board = new Board(trip, stop, sequence, depSec, walk);
                if (old == null || board.walkSec < old.walkSec || (board.walkSec == old.walkSec && board.departureSec > old.departureSec)) firstBoards.put(trip, board);
            }
        }
        if (firstBoards.isEmpty()) throw new Exception("No scheduled bus is reachable from the start point in the next six hours.");
        firstBoards = limitBoards(firstBoards, MAX_FIRST_TRIPS);

        Map<String, List<StopTime>> firstTimes = loadStopTimes(zip, firstBoards.keySet());
        List<Journey> journeys = new ArrayList<>();
        Map<String, List<TransferSeed>> transferSeeds = new HashMap<>();

        for (Board board : firstBoards.values()) {
            TripMeta trip = trips.get(board.tripId);
            List<StopTime> times = firstTimes.get(board.tripId);
            if (trip == null || times == null) continue;
            Collections.sort(times, Comparator.comparingInt(t -> t.sequence));
            StopTime boardTime = findStopTime(times, board.stopId, board.sequence);
            if (boardTime == null) continue;

            // Direct destination on the same trip.
            Journey bestDirect = null;
            for (StopTime st : times) {
                if (st.sequence <= boardTime.sequence || st.arrivalSec < board.departureSec) continue;
                Integer egress = destinationWalk.get(st.stopId);
                if (egress == null) continue;
                Ride ride = new Ride(trip, boardTime, st);
                Journey j = new Journey(ride, null, board.walkSec, egress, Math.max(now, board.departureSec - board.walkSec), st.arrivalSec + egress);
                if (bestDirect == null || j.arrivalSec < bestDirect.arrivalSec) bestDirect = j;
            }
            if (bestDirect != null) journeys.add(bestDirect);

            // Candidate same-stop transfers. Avoid retaining hundreds of remote stops per trip.
            int emitted = 0;
            for (StopTime st : times) {
                if (st.sequence <= boardTime.sequence || st.arrivalSec <= board.departureSec) continue;
                if (st.arrivalSec - board.departureSec > 95 * 60) break;
                Stop stop = stops.get(st.stopId);
                if (stop == null) continue;
                Ride firstRide = new Ride(trip, boardTime, st);
                List<TransferSeed> list = transferSeeds.computeIfAbsent(st.stopId, k -> new ArrayList<>());
                list.add(new TransferSeed(firstRide, board.walkSec, st.arrivalSec));
                list.sort(Comparator.comparingInt(s -> s.arrivalSec));
                while (list.size() > 5) list.remove(list.size() - 1);
                if (++emitted >= 30) break;
            }
        }

        // Pass 2: identify trips that can be boarded after a candidate transfer.
        Map<String, List<Board>> secondBoards = new HashMap<>();
        if (!transferSeeds.isEmpty()) {
            try (BufferedReader reader = entryReader(zip, "stop_times.txt")) {
                if (reader != null) {
                    List<String> header = csv(reader.readLine());
                    int tripId = indexOf(header, "trip_id"), stopId = indexOf(header, "stop_id"), seq = indexOf(header, "stop_sequence"), dep = indexOf(header, "departure_time");
                    String row; int scanned = 0;
                    while ((row = reader.readLine()) != null) {
                        if (((++scanned) & 2047) == 0 && Thread.currentThread().isInterrupted())
                            throw new InterruptedException("Route search cancelled");
                        List<String> c = csv(row);
                        String tripIdValue = value(c, tripId);
                        if (!trips.containsKey(tripIdValue)) continue;
                        String stop = value(c, stopId);
                        List<TransferSeed> seeds = transferSeeds.get(stop);
                        if (seeds == null) continue;
                        int departure = gtfsSeconds(value(c, dep));
                        if (departure < 0) continue;
                        boolean viable = false;
                        for (TransferSeed seed : seeds) {
                            if (seed.first.trip.tripId.equals(tripIdValue)) continue;
                            if (departure >= seed.arrivalSec + transferBuffer && departure <= seed.arrivalSec + 75 * 60) { viable = true; break; }
                        }
                        if (!viable) continue;
                        List<Board> list = secondBoards.computeIfAbsent(tripIdValue, k -> new ArrayList<>());
                        Board b = new Board(tripIdValue, stop, parseInt(value(c, seq), -1), departure, 0);
                        boolean duplicate = false;
                        for (Board old : list) if (old.stopId.equals(stop) && old.sequence == b.sequence) duplicate = true;
                        if (!duplicate) list.add(b);
                    }
                }
            }
        }
        secondBoards = limitSecondBoards(secondBoards, MAX_SECOND_TRIPS);
        Map<String, List<StopTime>> secondTimes = loadStopTimes(zip, secondBoards.keySet());

        for (Map.Entry<String, List<Board>> entry : secondBoards.entrySet()) {
            TripMeta secondTrip = trips.get(entry.getKey());
            List<StopTime> times = secondTimes.get(entry.getKey());
            if (secondTrip == null || times == null) continue;
            Collections.sort(times, Comparator.comparingInt(t -> t.sequence));
            for (Board board : entry.getValue()) {
                StopTime transferBoard = findStopTime(times, board.stopId, board.sequence);
                if (transferBoard == null) continue;
                List<TransferSeed> seeds = transferSeeds.get(board.stopId);
                if (seeds == null) continue;
                for (TransferSeed seed : seeds) {
                    if (seed.first.trip.tripId.equals(secondTrip.tripId)) continue;
                    if (transferBoard.departureSec < seed.arrivalSec + transferBuffer || transferBoard.departureSec > seed.arrivalSec + 75 * 60) continue;
                    for (StopTime destTime : times) {
                        if (destTime.sequence <= transferBoard.sequence || destTime.arrivalSec <= transferBoard.departureSec) continue;
                        Integer egress = destinationWalk.get(destTime.stopId);
                        if (egress == null) continue;
                        Ride secondRide = new Ride(secondTrip, transferBoard, destTime);
                        Journey j = new Journey(seed.first, secondRide, seed.accessWalkSec, egress, Math.max(now, seed.first.board.departureSec - seed.accessWalkSec), destTime.arrivalSec + egress);
                        journeys.add(j);
                        break; // earliest suitable destination stop on this boarding.
                    }
                }
            }
        }

        if (journeys.isEmpty()) {
            throw new Exception("OpenRoad could not find a suitable BODS bus journey for this search. Try another route or enable the optional TransportAPI fallback.");
        }

        int resultLimit = 3;
        List<Journey> ranked = rankAndDedupe(journeys, settings, resultLimit + 1);
        boolean hasMore = ranked.size() > resultLimit;
        if (hasMore) ranked = new ArrayList<>(ranked.subList(0, resultLimit));
        // Return the timetable result without waiting for the potentially large shapes.txt scan.
        // Stop-to-stop geometry is good enough for the first paint; exact published shapes are
        // added in a second local update by enrichGeometry().
        Map<String, List<ShapePoint>> shapes = Collections.emptyMap();

        JSONArray outRoutes = new JSONArray();
        int rank = 0;
        for (Journey j : ranked) {
            JSONObject built = buildRoute(j, originLat, originLon, destLat, destLon, stops, firstTimes, secondTimes, shapes, routes, walkSpeed, rank++);
            outRoutes.put(built);
            if (outRoutes.length() >= resultLimit) break;
        }
        return new JSONObject().put("routes", outRoutes).put("clearRoutePlanner", "BODS-local").put("clearRouteRegion", region).put("clearRouteHasMore", hasMore).put("clearRouteResultLimit", resultLimit);
    }

    private static JSONObject buildRoute(Journey journey,
                                         double originLat, double originLon, double destLat, double destLon,
                                         Map<String, Stop> stops,
                                         Map<String, List<StopTime>> firstTimes,
                                         Map<String, List<StopTime>> secondTimes,
                                         Map<String, List<ShapePoint>> shapes,
                                         Map<String, RouteMeta> routes,
                                         double walkSpeed, int rank) throws Exception {
        JSONArray legs = new JSONArray();
        JSONArray transitLegs = new JSONArray();
        JSONArray instructions = new JSONArray();
        long metres = 0;
        int pointIndex = 0;

        Stop firstBoardStop = stops.get(journey.first.board.stopId);
        if (firstBoardStop == null) throw new Exception("BODS boarding stop is missing from the timetable.");
        double accessDistance = distanceMetres(originLat, originLon, firstBoardStop.lat, firstBoardStop.lon);
        if (accessDistance > 20) {
            JSONArray points = straightPoints(originLat, originLon, firstBoardStop.lat, firstBoardStop.lon);
            legs.put(new JSONObject().put("points", points));
            transitLegs.put(walkLeg("Your location", firstBoardStop.name, originLat, originLon, firstBoardStop.lat, firstBoardStop.lon,
                    (int)Math.round(accessDistance / walkSpeed), accessDistance));
            instructions.put(instruction(pointIndex, metres, "Walk to " + firstBoardStop.name));
            metres += Math.round(accessDistance); pointIndex += points.length();
        }

        JSONArray firstPoints = ridePoints(journey.first, stops, firstTimes.get(journey.first.trip.tripId), shapes.get(journey.first.trip.shapeId));
        double firstDistance = polylineDistance(firstPoints);
        legs.put(new JSONObject().put("points", firstPoints));
        transitLegs.put(busLeg(journey.first, stops, routes, firstDistance));
        Stop firstAlight = stops.get(journey.first.alight.stopId);
        instructions.put(instruction(pointIndex, metres, "Bus " + lineLabel(journey.first.trip, routes) + " to " + (firstAlight == null ? "your stop" : firstAlight.name)));
        metres += Math.round(firstDistance); pointIndex += firstPoints.length();

        if (journey.second != null) {
            JSONArray secondPoints = ridePoints(journey.second, stops, secondTimes.get(journey.second.trip.tripId), shapes.get(journey.second.trip.shapeId));
            double secondDistance = polylineDistance(secondPoints);
            legs.put(new JSONObject().put("points", secondPoints));
            transitLegs.put(busLeg(journey.second, stops, routes, secondDistance));
            Stop secondAlight = stops.get(journey.second.alight.stopId);
            instructions.put(instruction(pointIndex, metres, "Change to bus " + lineLabel(journey.second.trip, routes) + " to " + (secondAlight == null ? "your stop" : secondAlight.name)));
            metres += Math.round(secondDistance); pointIndex += secondPoints.length();
        }

        Ride finalRide = journey.second == null ? journey.first : journey.second;
        Stop finalStop = stops.get(finalRide.alight.stopId);
        if (finalStop == null) throw new Exception("BODS destination stop is missing from the timetable.");
        double egressDistance = distanceMetres(finalStop.lat, finalStop.lon, destLat, destLon);
        if (egressDistance > 20) {
            JSONArray points = straightPoints(finalStop.lat, finalStop.lon, destLat, destLon);
            legs.put(new JSONObject().put("points", points));
            transitLegs.put(walkLeg(finalStop.name, "Destination", finalStop.lat, finalStop.lon, destLat, destLon,
                    (int)Math.round(egressDistance / walkSpeed), egressDistance));
            instructions.put(instruction(pointIndex, metres, "Walk to your destination"));
            metres += Math.round(egressDistance);
        }

        int travelSeconds = Math.max(60, journey.arrivalSec - journey.startSec);
        JSONObject summary = new JSONObject().put("travelTimeInSeconds", travelSeconds).put("lengthInMeters", metres);
        JSONObject out = new JSONObject()
                .put("summary", summary)
                .put("legs", legs)
                .put("transitLegs", transitLegs)
                .put("guidance", new JSONObject().put("instructions", instructions))
                .put("clearRouteTransit", true)
                .put("clearRouteLabel", rank == 0 ? "Recommended" : "Public transport alternative")
                .put("clearRouteDeparture", displayClock(journey.startSec))
                .put("clearRouteArrival", displayClock(journey.arrivalSec))
                .put("clearRouteDataStatus", "scheduled")
                .put("clearRouteLiveStatus", "loading")
                .put("clearRouteDataSource", "DfT BODS GTFS")
                .put("clearRouteDataNote", "OpenRoad local journey planning from the official DfT/BODS timetable · walking access is estimated");
        if (journey.second != null) out.put("clearRouteWarning", "1 change · allow " + Math.max(1, (journey.second.board.departureSec - journey.first.alight.arrivalSec) / 60) + " min at the interchange");
        return out;
    }

    /** Add exact published BODS shape geometry after the first timetable result has been shown. */
    public static boolean enrichGeometry(Context context, JSONObject response) throws Exception {
        if (response == null) return false;
        String region = response.optString("clearRouteRegion", "");
        if (region.isEmpty()) return false;
        JSONArray routesJson = response.optJSONArray("routes");
        if (routesJson == null || routesJson.length() == 0) return false;
        Set<String> wanted = new HashSet<>();
        for (int ri=0;ri<routesJson.length();ri++) {
            JSONObject route=routesJson.optJSONObject(ri); if(route==null) continue;
            JSONArray tlegs=route.optJSONArray("transitLegs"); if(tlegs==null) continue;
            for(int li=0;li<tlegs.length();li++){
                JSONObject leg=tlegs.optJSONObject(li); if(leg==null || !"bus".equals(leg.optString("mode"))) continue;
                String sid=leg.optString("shapeId",""); if(!sid.isEmpty()) wanted.add(sid);
            }
        }
        if(wanted.isEmpty()) {
            boolean changed=false;
            for(int ri=0;ri<routesJson.length();ri++){JSONObject route=routesJson.optJSONObject(ri);JSONArray tlegs=route==null?null:route.optJSONArray("transitLegs");if(tlegs==null)continue;for(int li=0;li<tlegs.length();li++){JSONObject leg=tlegs.optJSONObject(li);if(leg!=null&&"bus".equals(leg.optString("mode"))&&"loading".equals(leg.optString("geometryStatus"))){leg.put("geometryStatus","fallback");changed=true;}}}
            return changed;
        }
        File zip=ensureRegion(context,region);
        Map<String,List<ShapePoint>> shapes=loadShapes(zip,wanted);
        boolean changed=false;
        for (int ri=0;ri<routesJson.length();ri++) {
            JSONObject route=routesJson.optJSONObject(ri); if(route==null) continue;
            JSONArray tlegs=route.optJSONArray("transitLegs"), legs=route.optJSONArray("legs");
            if(tlegs==null||legs==null) continue;
            int n=Math.min(tlegs.length(),legs.length());
            for(int li=0;li<n;li++){
                JSONObject tleg=tlegs.optJSONObject(li), mapLeg=legs.optJSONObject(li);
                if(tleg==null||mapLeg==null||!"bus".equals(tleg.optString("mode"))) continue;
                List<ShapePoint> shape=shapes.get(tleg.optString("shapeId",""));
                if(shape==null||shape.size()<2){if("loading".equals(tleg.optString("geometryStatus"))){tleg.put("geometryStatus","fallback");changed=true;}continue;}
                double fromLat=tleg.optDouble("fromLat",Double.NaN),fromLon=tleg.optDouble("fromLon",Double.NaN),toLat=tleg.optDouble("toLat",Double.NaN),toLon=tleg.optDouble("toLon",Double.NaN);
                if(!Double.isFinite(fromLat)||!Double.isFinite(fromLon)||!Double.isFinite(toLat)||!Double.isFinite(toLon)){tleg.put("geometryStatus","fallback");changed=true;continue;}
                int a=nearestShapeIndex(shape,fromLat,fromLon),b=nearestShapeIndex(shape,toLat,toLon);
                if(a<0||b<=a){tleg.put("geometryStatus","fallback");changed=true;continue;}
                JSONArray points=new JSONArray(); int step=Math.max(1,(b-a)/180);
                for(int i=a;i<=b;i+=step)points.put(point(shape.get(i).lat,shape.get(i).lon));
                ShapePoint end=shape.get(b); points.put(point(end.lat,end.lon));
                if(points.length()>=2){mapLeg.put("points",points);tleg.put("geometryStatus","exact");changed=true;}else{tleg.put("geometryStatus","fallback");changed=true;}
            }
        }
        return changed;
    }

    private static JSONObject walkLeg(String from, String to, double fromLat, double fromLon, double toLat, double toLon, int seconds, double metres) throws Exception {
        return new JSONObject().put("mode", "foot").put("from", from).put("to", to)
                .put("fromLat", fromLat).put("fromLon", fromLon).put("toLat", toLat).put("toLon", toLon)
                .put("durationSeconds", Math.max(1, seconds)).put("distanceMetres", Math.round(metres))
                .put("timeStatus", "scheduled").put("dataSource", "OpenRoad walking estimate")
                .put("geometryStatus", metres > 25 ? "loading" : "exact");
    }

    private static JSONObject busLeg(Ride ride, Map<String, Stop> stops, Map<String, RouteMeta> routes, double metres) throws Exception {
        Stop from = stops.get(ride.board.stopId), to = stops.get(ride.alight.stopId);
        String line = lineLabel(ride.trip, routes);
        String destination = ride.trip.headsign;
        if ((destination == null || destination.isEmpty()) && to != null) destination = to.name;
        return new JSONObject().put("mode", "bus").put("line", line).put("destination", destination == null ? "" : destination)
                .put("from", from == null ? "Bus stop" : from.name).put("to", to == null ? "Bus stop" : to.name)
                .put("fromAtco", ride.board.stopId).put("toAtco", ride.alight.stopId)
                .put("fromLat", from == null ? JSONObject.NULL : from.lat).put("fromLon", from == null ? JSONObject.NULL : from.lon)
                .put("toLat", to == null ? JSONObject.NULL : to.lat).put("toLon", to == null ? JSONObject.NULL : to.lon)
                .put("departure", displayClock(ride.board.departureSec)).put("arrival", displayClock(ride.alight.arrivalSec))
                .put("durationSeconds", Math.max(60, ride.alight.arrivalSec - ride.board.departureSec))
                .put("distanceMetres", Math.round(metres)).put("stopCount", Math.max(1, ride.alight.sequence - ride.board.sequence))
                .put("shapeId", ride.trip.shapeId == null ? "" : ride.trip.shapeId)
                .put("geometryStatus", "loading")
                .put("timeStatus", "scheduled").put("dataSource", "DfT BODS GTFS");
    }

    private static JSONObject instruction(int pointIndex, long offset, String message) throws Exception {
        return new JSONObject().put("pointIndex", pointIndex).put("routeOffsetInMeters", offset)
                .put("travelTimeInSeconds", 0).put("message", message).put("maneuver", "STRAIGHT")
                .put("instructionType", "TRANSIT");
    }

    private static JSONArray ridePoints(Ride ride, Map<String, Stop> stops, List<StopTime> times, List<ShapePoint> shape) throws Exception {
        Stop from = stops.get(ride.board.stopId), to = stops.get(ride.alight.stopId);
        if (shape != null && shape.size() >= 2 && from != null && to != null) {
            int a = nearestShapeIndex(shape, from.lat, from.lon), b = nearestShapeIndex(shape, to.lat, to.lon);
            if (a >= 0 && b > a) {
                JSONArray out = new JSONArray();
                int step = Math.max(1, (b - a) / 160);
                for (int i = a; i <= b; i += step) out.put(point(shape.get(i).lat, shape.get(i).lon));
                ShapePoint end = shape.get(b);
                if (out.length() == 0 || Math.abs(out.optJSONObject(out.length()-1).optDouble("latitude") - end.lat) > 1e-8 || Math.abs(out.optJSONObject(out.length()-1).optDouble("longitude") - end.lon) > 1e-8) out.put(point(end.lat, end.lon));
                if (out.length() >= 2) return out;
            }
        }
        JSONArray out = new JSONArray();
        if (times != null) {
            for (StopTime st : times) {
                if (st.sequence < ride.board.sequence || st.sequence > ride.alight.sequence) continue;
                Stop s = stops.get(st.stopId); if (s != null) out.put(point(s.lat, s.lon));
            }
        }
        if (out.length() < 2 && from != null && to != null) return straightPoints(from.lat, from.lon, to.lat, to.lon);
        return out;
    }

    private static JSONArray straightPoints(double lat1, double lon1, double lat2, double lon2) throws Exception {
        return new JSONArray().put(point(lat1, lon1)).put(point(lat2, lon2));
    }

    private static JSONObject point(double lat, double lon) throws Exception { return new JSONObject().put("latitude", lat).put("longitude", lon); }

    private static int nearestShapeIndex(List<ShapePoint> shape, double lat, double lon) {
        int best = -1; double d = Double.POSITIVE_INFINITY;
        for (int i = 0; i < shape.size(); i++) {
            ShapePoint p = shape.get(i); double x = distanceMetres(lat, lon, p.lat, p.lon);
            if (x < d) { d = x; best = i; }
        }
        return best;
    }

    private static double polylineDistance(JSONArray points) {
        double total = 0;
        for (int i = 1; i < points.length(); i++) {
            JSONObject a = points.optJSONObject(i-1), b = points.optJSONObject(i); if (a == null || b == null) continue;
            total += distanceMetres(a.optDouble("latitude"), a.optDouble("longitude"), b.optDouble("latitude"), b.optDouble("longitude"));
        }
        return total;
    }

    private static List<Journey> rankAndDedupe(List<Journey> journeys, JSONObject settings, int limit) {
        String ranking = settings == null ? "balanced" : settings.optString("ranking", "balanced");
        int penalty = settings != null && "cautious".equals(settings.optString("transferBuffer", "normal")) ? 12 * 60 : 8 * 60;
        journeys.sort((a,b) -> Long.compare(score(a, ranking, penalty), score(b, ranking, penalty)));
        List<Journey> out = new ArrayList<>(); Set<String> signatures = new HashSet<>();
        for (Journey j : journeys) {
            String sig = j.signature();
            if (!signatures.add(sig)) continue;
            out.add(j); if (out.size() >= limit) break;
        }
        return out;
    }

    private static long score(Journey j, String ranking, int transferPenalty) {
        long arrival = j.arrivalSec; int changes = j.second == null ? 0 : 1; long walk = j.accessWalkSec + j.egressWalkSec;
        if ("quickest".equals(ranking)) return arrival + walk / 50L;
        if ("changes".equals(ranking)) return changes * 10_000_000L + arrival + Math.round(walk * 0.35);
        // Balanced deliberately gives walking meaningful weight: a five-minute extra walk should
        // need a materially earlier arrival to beat an otherwise similar stop beside the user.
        return arrival + changes * (long)transferPenalty + Math.round(walk * 0.80);
    }

    private static Map<String, Board> limitBoards(Map<String, Board> source, int limit) {
        List<Board> list = new ArrayList<>(source.values()); list.sort(Comparator.comparingInt(b -> b.departureSec));
        Map<String, Board> out = new LinkedHashMap<>(); for (Board b : list) { out.put(b.tripId,b); if(out.size()>=limit)break; } return out;
    }

    private static Map<String, List<Board>> limitSecondBoards(Map<String, List<Board>> source, int limit) {
        List<Map.Entry<String,List<Board>>> entries = new ArrayList<>(source.entrySet());
        entries.sort(Comparator.comparingInt(e -> e.getValue().stream().mapToInt(b -> b.departureSec).min().orElse(Integer.MAX_VALUE)));
        Map<String,List<Board>> out = new LinkedHashMap<>(); for (Map.Entry<String,List<Board>> e:entries){out.put(e.getKey(),e.getValue());if(out.size()>=limit)break;} return out;
    }

    private static StopTime findStopTime(List<StopTime> times, String stopId, int sequence) {
        if (times == null) return null;
        for (StopTime st : times) if (st.stopId.equals(stopId) && (sequence < 0 || st.sequence == sequence)) return st;
        return null;
    }

    private static String metaFileKey(File zip) {
        return zip.getAbsolutePath() + "|" + zip.length() + "|" + zip.lastModified();
    }

    private static Map<String,Stop> loadStopsCached(File zip) throws Exception {
        String key = metaFileKey(zip);
        synchronized (META_CACHE_LOCK) {
            if (key.equals(cachedMetaFileKey) && cachedStops != null) return cachedStops;
            if (!key.equals(cachedMetaFileKey)) {
                cachedMetaFileKey = key; cachedStops = null; cachedRoutes = null; cachedTrips = null; cachedTripDate = null;
            }
            cachedStops = loadStops(zip);
            return cachedStops;
        }
    }

    private static Map<String,RouteMeta> loadRoutesCached(File zip) throws Exception {
        String key = metaFileKey(zip);
        synchronized (META_CACHE_LOCK) {
            if (key.equals(cachedMetaFileKey) && cachedRoutes != null) return cachedRoutes;
            if (!key.equals(cachedMetaFileKey)) {
                cachedMetaFileKey = key; cachedStops = null; cachedRoutes = null; cachedTrips = null; cachedTripDate = null;
            }
            cachedRoutes = loadRoutes(zip);
            return cachedRoutes;
        }
    }

    private static Map<String,TripMeta> loadActiveTripsCached(File zip, LocalDate date) throws Exception {
        String key = metaFileKey(zip);
        synchronized (META_CACHE_LOCK) {
            if (key.equals(cachedMetaFileKey) && date.equals(cachedTripDate) && cachedTrips != null) return cachedTrips;
            if (!key.equals(cachedMetaFileKey)) {
                cachedMetaFileKey = key; cachedStops = null; cachedRoutes = null; cachedTrips = null; cachedTripDate = null;
            }
            boolean hasCalendar = entryExists(zip, "calendar.txt") || entryExists(zip, "calendar_dates.txt");
            Set<String> activeServices = activeServiceIds(zip, date);
            cachedTrips = loadActiveTrips(zip, activeServices, hasCalendar);
            cachedTripDate = date;
            return cachedTrips;
        }
    }

    private static Map<String,List<StopTime>> loadStopTimes(File zip, Set<String> wantedTrips) throws Exception {
        Map<String,List<StopTime>> out = new HashMap<>(); if (wantedTrips == null || wantedTrips.isEmpty()) return out;
        try (BufferedReader reader = entryReader(zip,"stop_times.txt")) {
            if (reader == null) return out; List<String> header=csv(reader.readLine());
            int trip=indexOf(header,"trip_id"), stop=indexOf(header,"stop_id"), seq=indexOf(header,"stop_sequence"), arr=indexOf(header,"arrival_time"), dep=indexOf(header,"departure_time");
            String row; int scanned=0; while((row=reader.readLine())!=null){if(((++scanned)&2047)==0 && Thread.currentThread().isInterrupted())throw new InterruptedException("Route search cancelled");List<String> c=csv(row);String tid=value(c,trip);if(!wantedTrips.contains(tid))continue;int a=gtfsSeconds(value(c,arr)),d=gtfsSeconds(value(c,dep));if(a<0)a=d;if(d<0)d=a;if(a<0||d<0)continue;out.computeIfAbsent(tid,k->new ArrayList<>()).add(new StopTime(value(c,stop),parseInt(value(c,seq),-1),a,d));}
        }
        return out;
    }

    private static Map<String,TripMeta> loadActiveTrips(File zip, Set<String> activeServices, boolean hasCalendar) throws Exception {
        Map<String,TripMeta> out=new HashMap<>();
        try(BufferedReader reader=entryReader(zip,"trips.txt")){if(reader==null)return out;List<String> h=csv(reader.readLine());int trip=indexOf(h,"trip_id"),route=indexOf(h,"route_id"),service=indexOf(h,"service_id"),head=indexOf(h,"trip_headsign"),shape=indexOf(h,"shape_id"),direction=indexOf(h,"direction_id");String row;while((row=reader.readLine())!=null){List<String> c=csv(row);String sid=value(c,service);if(hasCalendar&&!activeServices.contains(sid))continue;String id=value(c,trip);if(id.isEmpty())continue;out.put(id,new TripMeta(id,value(c,route),sid,value(c,head),value(c,shape),value(c,direction)));}}
        return out;
    }

    private static Map<String,RouteMeta> loadRoutes(File zip) throws Exception {
        Map<String,RouteMeta> out=new HashMap<>();
        try(BufferedReader reader=entryReader(zip,"routes.txt")){if(reader==null)return out;List<String> h=csv(reader.readLine());int id=indexOf(h,"route_id"),shortName=indexOf(h,"route_short_name"),longName=indexOf(h,"route_long_name"),type=indexOf(h,"route_type");String row;while((row=reader.readLine())!=null){List<String> c=csv(row);String rid=value(c,id);if(rid.isEmpty())continue;out.put(rid,new RouteMeta(value(c,shortName),value(c,longName),value(c,type)));}}
        return out;
    }

    private static Map<String,Stop> loadStops(File zip) throws Exception {
        Map<String,Stop> out=new HashMap<>();
        try(BufferedReader reader=entryReader(zip,"stops.txt")){if(reader==null)return out;List<String> h=csv(reader.readLine());int id=indexOf(h,"stop_id"),name=indexOf(h,"stop_name"),lat=indexOf(h,"stop_lat"),lon=indexOf(h,"stop_lon");String row;while((row=reader.readLine())!=null){List<String> c=csv(row);try{String sid=value(c,id);if(sid.isEmpty())continue;out.put(sid,new Stop(sid,value(c,name),Double.parseDouble(value(c,lat)),Double.parseDouble(value(c,lon))));}catch(Exception ignored){}}}
        return out;
    }

    private static Map<String,Integer> nearbyStops(Map<String,Stop> stops,double lat,double lon,double radius,double walkSpeed,int limit){
        List<StopDistance> list=new ArrayList<>();for(Stop s:stops.values()){double d=distanceMetres(lat,lon,s.lat,s.lon);if(d<=radius)list.add(new StopDistance(s.id,d));}
        list.sort(Comparator.comparingDouble(s->s.distance));Map<String,Integer> out=new LinkedHashMap<>();for(StopDistance d:list){out.put(d.stopId,(int)Math.ceil(d.distance/walkSpeed));if(out.size()>=limit)break;}return out;
    }

    private static Map<String,List<ShapePoint>> loadShapes(File zip,Set<String>wanted)throws Exception{
        Map<String,List<ShapePoint>> out=new HashMap<>();if(wanted==null||wanted.isEmpty())return out;for(String id:wanted)out.put(id,new ArrayList<>());
        try(BufferedReader reader=entryReader(zip,"shapes.txt")){if(reader==null)return out;List<String> h=csv(reader.readLine());int id=indexOf(h,"shape_id"),lat=indexOf(h,"shape_pt_lat"),lon=indexOf(h,"shape_pt_lon"),seq=indexOf(h,"shape_pt_sequence");String row;while((row=reader.readLine())!=null){List<String> c=csv(row);String sid=value(c,id);List<ShapePoint> list=out.get(sid);if(list==null)continue;try{list.add(new ShapePoint(parseInt(value(c,seq),0),Double.parseDouble(value(c,lat)),Double.parseDouble(value(c,lon))));}catch(Exception ignored){}}}
        for(List<ShapePoint> list:out.values())list.sort(Comparator.comparingInt(p->p.sequence));return out;
    }

    private static Set<String> activeServiceIds(File zipFile, LocalDate date) {
        Set<String> active=new HashSet<>();
        try(BufferedReader reader=entryReader(zipFile,"calendar.txt")){if(reader!=null){List<String> h=csv(reader.readLine());int service=indexOf(h,"service_id"),start=indexOf(h,"start_date"),end=indexOf(h,"end_date"),day=indexOf(h,date.getDayOfWeek().name().toLowerCase(Locale.UK));String row;while((row=reader.readLine())!=null){List<String> c=csv(row);try{LocalDate a=LocalDate.parse(value(c,start),DateTimeFormatter.BASIC_ISO_DATE),b=LocalDate.parse(value(c,end),DateTimeFormatter.BASIC_ISO_DATE);if(!date.isBefore(a)&&!date.isAfter(b)&&"1".equals(value(c,day)))active.add(value(c,service));}catch(Exception ignored){}}}}catch(Exception ignored){}
        try(BufferedReader reader=entryReader(zipFile,"calendar_dates.txt")){if(reader!=null){List<String> h=csv(reader.readLine());int service=indexOf(h,"service_id"),dateIdx=indexOf(h,"date"),type=indexOf(h,"exception_type");String target=date.format(DateTimeFormatter.BASIC_ISO_DATE),row;while((row=reader.readLine())!=null){List<String> c=csv(row);if(!target.equals(value(c,dateIdx)))continue;if("1".equals(value(c,type)))active.add(value(c,service));else if("2".equals(value(c,type)))active.remove(value(c,service));}}}catch(Exception ignored){}
        return active;
    }

    private static boolean modeEnabled(JSONObject settings,String mode){if(settings==null)return true;JSONObject modes=settings.optJSONObject("modes");return modes==null||modes.optBoolean(mode,true);}
    private static double walkSpeed(JSONObject settings){String s=settings==null?"normal":settings.optString("walkSpeed","normal");return "slow".equals(s)?1.05:"fast".equals(s)?1.65:1.35;}
    private static int transferBuffer(JSONObject settings){return settings!=null&&"cautious".equals(settings.optString("transferBuffer","normal"))?8*60:3*60;}
    private static String lineLabel(TripMeta trip,Map<String,RouteMeta>routes){RouteMeta r=routes.get(trip.routeId);if(r==null)return "Bus";if(r.shortName!=null&&!r.shortName.trim().isEmpty())return r.shortName.trim();if(r.longName!=null&&!r.longName.trim().isEmpty())return r.longName.trim();return "Bus";}
    private static String displayClock(int sec){sec=((sec%86400)+86400)%86400;return String.format(Locale.UK,"%02d:%02d",sec/3600,(sec%3600)/60);}
    private static int gtfsSeconds(String value){try{String[]p=value.split(":");if(p.length<2)return-1;return Integer.parseInt(p[0])*3600+Integer.parseInt(p[1])*60+(p.length>2?Integer.parseInt(p[2]):0);}catch(Exception e){return-1;}}
    private static int parseInt(String value,int fallback){try{return Integer.parseInt(value);}catch(Exception e){return fallback;}}

    private static double distanceMetres(double lat1,double lon1,double lat2,double lon2){double x=Math.toRadians(lon2-lon1)*Math.cos(Math.toRadians((lat1+lat2)/2.0));double y=Math.toRadians(lat2-lat1);return Math.sqrt(x*x+y*y)*6371000.0;}

    private static String commonRegion(String a,String b){if(a.equals(b))return a;Set<String> england=new HashSet<>();Collections.addAll(england,"north_east","north_west","east_anglia","east_midlands","south_east","south_west","england");if(england.contains(a)&&england.contains(b))return "england";return null;}
    private static String regionFor(double lat,double lon){if(lat>=54.63)return"scotland";if(lat>=51.25&&lat<=53.55&&lon<=-2.65&&(lon<=-3.00||lat>=52.05))return"wales";if(lat>=54.10)return"north_east";if(lat>=52.70&&lon<=-1.45)return"north_west";if(lat>=52.05&&lon>=0.20)return"east_anglia";if(lat>=52.05&&lon>-1.45)return"east_midlands";if(lat<52.20&&lon>=-1.15)return"south_east";if(lat<52.20)return"south_west";return"england";}

    private static File ensureRegion(Context context,String region)throws Exception{
        synchronized(REGION_FILE_LOCK){
            File dir=new File(context.getCacheDir(),"transit/bods-gtfs");
            if(!dir.exists()&&!dir.mkdirs())throw new Exception("Could not create BODS cache");
            File target=new File(dir,region+".zip");
            if(target.exists()&&target.length()>1024&&System.currentTimeMillis()-target.lastModified()<MAX_AGE_MS)return target;
            File temp=new File(dir,region+".download");if(temp.exists())temp.delete();
            download(BASE+region+"/",temp);
            if(temp.length()<1024){temp.delete();throw new Exception("BODS GTFS download was empty");}
            if(target.exists()&&!target.delete())throw new Exception("Could not refresh BODS cache");
            if(!temp.renameTo(target)){copy(temp,target);temp.delete();}
            synchronized(META_CACHE_LOCK){cachedMetaFileKey="";cachedStops=null;cachedRoutes=null;cachedTrips=null;cachedTripDate=null;}
            return target;
        }
    }
    private static void download(String url,File destination)throws Exception{HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setConnectTimeout(15000);c.setReadTimeout(60000);c.setInstanceFollowRedirects(true);c.setRequestProperty("Accept","application/zip, application/octet-stream, */*");c.setRequestProperty("User-Agent","OpenRoad-Android/0.6.27");int status=c.getResponseCode();if(status<200||status>=300){c.disconnect();throw new Exception("BODS GTFS returned HTTP "+status);}try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(destination)){byte[]buf=new byte[32768];int n;while((n=in.read(buf))>=0)out.write(buf,0,n);}finally{c.disconnect();}}
    private static void copy(File source,File destination)throws Exception{try(InputStream in=new FileInputStream(source);FileOutputStream out=new FileOutputStream(destination)){byte[]buf=new byte[32768];int n;while((n=in.read(buf))>=0)out.write(buf,0,n);}}
    private static boolean entryExists(File zip,String wanted){try(ZipInputStream z=new ZipInputStream(new FileInputStream(zip),StandardCharsets.UTF_8)){ZipEntry e;String w=wanted.toLowerCase(Locale.UK);while((e=z.getNextEntry())!=null){String n=e.getName().toLowerCase(Locale.UK);if(n.equals(w)||n.endsWith("/"+w))return true;}}catch(Exception ignored){}return false;}
    private static BufferedReader entryReader(File zip,String wanted)throws Exception{ZipInputStream z=new ZipInputStream(new FileInputStream(zip),StandardCharsets.UTF_8);ZipEntry e;String w=wanted.toLowerCase(Locale.UK);while((e=z.getNextEntry())!=null){String n=e.getName().toLowerCase(Locale.UK);if(n.equals(w)||n.endsWith("/"+w))return new BufferedReader(new InputStreamReader(z,StandardCharsets.UTF_8));}z.close();return null;}
    private static int indexOf(List<String> h,String name){for(int i=0;i<h.size();i++)if(name.equalsIgnoreCase(h.get(i).replace("\ufeff","").trim()))return i;return-1;}
    private static String value(List<String>c,int i){return i>=0&&i<c.size()?c.get(i).trim():"";}
    private static List<String> csv(String line){List<String>out=new ArrayList<>();if(line==null)return out;StringBuilder cell=new StringBuilder();boolean q=false;for(int i=0;i<line.length();i++){char ch=line.charAt(i);if(ch=='\"'){if(q&&i+1<line.length()&&line.charAt(i+1)=='\"'){cell.append('\"');i++;}else q=!q;}else if(ch==','&&!q){out.add(cell.toString());cell.setLength(0);}else cell.append(ch);}out.add(cell.toString());return out;}

    private static final class Stop { final String id,name; final double lat,lon; Stop(String id,String name,double lat,double lon){this.id=id;this.name=name==null||name.trim().isEmpty()?"Bus stop":name.trim();this.lat=lat;this.lon=lon;} }
    private static final class StopDistance { final String stopId; final double distance; StopDistance(String stopId,double distance){this.stopId=stopId;this.distance=distance;} }
    private static final class TripMeta { final String tripId,routeId,serviceId,headsign,shapeId,direction; TripMeta(String tripId,String routeId,String serviceId,String headsign,String shapeId,String direction){this.tripId=tripId;this.routeId=routeId;this.serviceId=serviceId;this.headsign=headsign==null?"":headsign;this.shapeId=shapeId==null?"":shapeId;this.direction=direction==null?"":direction;} }
    private static final class RouteMeta { final String shortName,longName,type; RouteMeta(String shortName,String longName,String type){this.shortName=shortName;this.longName=longName;this.type=type;} }
    private static final class Board { final String tripId,stopId; final int sequence,departureSec,walkSec; Board(String tripId,String stopId,int sequence,int departureSec,int walkSec){this.tripId=tripId;this.stopId=stopId;this.sequence=sequence;this.departureSec=departureSec;this.walkSec=walkSec;} }
    private static final class StopTime { final String stopId; final int sequence,arrivalSec,departureSec; StopTime(String stopId,int sequence,int arrivalSec,int departureSec){this.stopId=stopId;this.sequence=sequence;this.arrivalSec=arrivalSec;this.departureSec=departureSec;} }
    private static final class Ride { final TripMeta trip; final StopTime board,alight; Ride(TripMeta trip,StopTime board,StopTime alight){this.trip=trip;this.board=board;this.alight=alight;} }
    private static final class TransferSeed { final Ride first; final int accessWalkSec,arrivalSec; TransferSeed(Ride first,int accessWalkSec,int arrivalSec){this.first=first;this.accessWalkSec=accessWalkSec;this.arrivalSec=arrivalSec;} }
    private static final class Journey { final Ride first,second; final int accessWalkSec,egressWalkSec,startSec,arrivalSec; Journey(Ride first,Ride second,int accessWalkSec,int egressWalkSec,int startSec,int arrivalSec){this.first=first;this.second=second;this.accessWalkSec=accessWalkSec;this.egressWalkSec=egressWalkSec;this.startSec=startSec;this.arrivalSec=arrivalSec;} String signature(){return first.trip.routeId+"|"+first.board.stopId+"|"+first.alight.stopId+(second==null?"":"|"+second.trip.routeId+"|"+second.board.stopId+"|"+second.alight.stopId);} }
    private static final class ShapePoint { final int sequence; final double lat,lon; ShapePoint(int sequence,double lat,double lon){this.sequence=sequence;this.lat=lat;this.lon=lon;} }
}
