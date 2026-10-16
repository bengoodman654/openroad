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
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Small on-demand cache/reader for the DfT BODS GTFS schedule downloads.
 *
 * The DfT publishes national and regional GTFS downloads which are refreshed daily. OpenRoad
 * keeps only the relevant regional ZIP in Android's cache directory and refreshes it after 24h.
 * The ZIP is never unpacked permanently: routes/trips/shapes are streamed when a bus number is
 * requested, which keeps local storage and privacy impact modest.
 */
public final class BodsGtfsCache {
    private static final long MAX_AGE_MS = 24L * 60L * 60L * 1000L;
    private static final String BASE = "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/";

    private BodsGtfsCache() {}

    /** Returns a scheduled bus route geometry near the supplied coordinate, or null if unavailable. */
    public static JSONObject findBusRoute(Context context, double lat, double lon, String line) {
        String region = regionFor(lat, lon);
        try {
            File zip = ensureRegion(context, region);
            JSONObject result = parseRoute(zip, lat, lon, line);
            if (result != null) {
                result.put("source", "BODS GTFS");
                result.put("scheduleSource", "DfT Bus Open Data Service");
                result.put("coverage", "scheduled-route");
                result.put("region", region);
                result.put("cacheUpdated", zip.lastModified());
            }
            return result;
        } catch (Exception ignored) {
            return null;
        }
    }

    public static JSONObject status(Context context) {
        JSONObject out = new JSONObject();
        try {
            File dir = new File(context.getCacheDir(), "transit/bods-gtfs");
            File[] files = dir.listFiles((d, name) -> name.endsWith(".zip"));
            JSONArray regions = new JSONArray();
            long newest = 0L;
            if (files != null) {
                for (File f : files) {
                    regions.put(f.getName().replace(".zip", ""));
                    newest = Math.max(newest, f.lastModified());
                }
            }
            out.put("regions", regions);
            out.put("lastUpdated", newest);
        } catch (Exception ignored) {}
        return out;
    }

    private static File ensureRegion(Context context, String region) throws Exception {
        File dir = new File(context.getCacheDir(), "transit/bods-gtfs");
        if (!dir.exists() && !dir.mkdirs()) throw new Exception("Could not create BODS cache");
        File target = new File(dir, region + ".zip");
        if (target.exists() && target.length() > 1024 && System.currentTimeMillis() - target.lastModified() < MAX_AGE_MS)
            return target;

        File temp = new File(dir, region + ".download");
        if (temp.exists()) temp.delete();
        download(BASE + region + "/", temp);
        if (temp.length() < 1024) {
            temp.delete();
            throw new Exception("BODS GTFS download was empty");
        }
        if (target.exists() && !target.delete()) throw new Exception("Could not refresh BODS cache");
        if (!temp.renameTo(target)) {
            copy(temp, target);
            temp.delete();
        }
        return target;
    }

    private static JSONObject parseRoute(File zipFile, double queryLat, double queryLon, String requestedLine) throws Exception {
        String cleanLine = normaliseLine(requestedLine);
        if (cleanLine.isEmpty()) return null;

        Set<String> routeIds = new HashSet<>();
        Map<String, String> routeLabels = new HashMap<>();
        try (BufferedReader reader = entryReader(zipFile, "routes.txt")) {
            if (reader == null) return null;
            String headerLine = reader.readLine();
            if (headerLine == null) return null;
            List<String> header = csv(headerLine);
            int routeId = indexOf(header, "route_id");
            int shortName = indexOf(header, "route_short_name");
            int longName = indexOf(header, "route_long_name");
            String row;
            while ((row = reader.readLine()) != null) {
                List<String> cols = csv(row);
                String id = value(cols, routeId);
                String shortLabel = value(cols, shortName);
                String longLabel = value(cols, longName);
                if (!id.isEmpty() && routeMatches(cleanLine, shortLabel, longLabel)) {
                    routeIds.add(id);
                    routeLabels.put(id, !shortLabel.isEmpty() ? shortLabel : longLabel);
                }
            }
        }
        if (routeIds.isEmpty()) return null;

        // A public line number such as "1" occurs in many towns. Keep up to two representative
        // shapes per matching route_id, then choose the route whose geometry is closest to the
        // caller's location. This prevents Bristol's "1" from accidentally drawing another city's.
        Map<String, List<String>> routeShapes = new HashMap<>();
        Map<String, String> shapeDirection = new HashMap<>();
        Map<String, String> shapeRoute = new HashMap<>();
        Map<String, String> shapeTrip = new HashMap<>();
        try (BufferedReader reader = entryReader(zipFile, "trips.txt")) {
            if (reader == null) return null;
            List<String> header = csv(reader.readLine());
            int routeId = indexOf(header, "route_id");
            int shapeId = indexOf(header, "shape_id");
            int directionId = indexOf(header, "direction_id");
            int tripId = indexOf(header, "trip_id");
            String row;
            while ((row = reader.readLine()) != null) {
                List<String> cols = csv(row);
                String rid = value(cols, routeId);
                String sid = value(cols, shapeId);
                if (!routeIds.contains(rid) || sid.isEmpty()) continue;
                List<String> selected = routeShapes.computeIfAbsent(rid, k -> new ArrayList<>());
                String direction = "1".equals(value(cols, directionId)) ? "inbound" : "outbound";
                boolean alreadyDirection = false;
                for (String oldSid : selected) if (direction.equals(shapeDirection.get(oldSid))) alreadyDirection = true;
                if (!selected.contains(sid) && (selected.size() < 2) && (!alreadyDirection || selected.isEmpty())) {
                    selected.add(sid);
                    shapeDirection.put(sid, direction);
                    shapeRoute.put(sid, rid);
                    shapeTrip.put(sid, value(cols, tripId));
                }
            }
        }
        if (shapeRoute.isEmpty()) return null;

        Map<String, List<ShapePoint>> points = new HashMap<>();
        Map<String, Double> nearestByRoute = new HashMap<>();
        for (String sid : shapeRoute.keySet()) points.put(sid, new ArrayList<>());
        try (BufferedReader reader = entryReader(zipFile, "shapes.txt")) {
            if (reader == null) return null;
            List<String> header = csv(reader.readLine());
            int shapeId = indexOf(header, "shape_id");
            int lat = indexOf(header, "shape_pt_lat");
            int lon = indexOf(header, "shape_pt_lon");
            int seq = indexOf(header, "shape_pt_sequence");
            String row;
            while ((row = reader.readLine()) != null) {
                List<String> cols = csv(row);
                String sid = value(cols, shapeId);
                List<ShapePoint> list = points.get(sid);
                if (list == null) continue;
                try {
                    double pointLat = Double.parseDouble(value(cols, lat));
                    double pointLon = Double.parseDouble(value(cols, lon));
                    list.add(new ShapePoint(Integer.parseInt(value(cols, seq)), pointLat, pointLon));
                    String rid = shapeRoute.get(sid);
                    double d = approxDistanceMetres(queryLat, queryLon, pointLat, pointLon);
                    Double previous = nearestByRoute.get(rid);
                    if (previous == null || d < previous) nearestByRoute.put(rid, d);
                } catch (Exception ignored) {}
            }
        }

        String selectedRoute = null;
        double selectedDistance = Double.POSITIVE_INFINITY;
        for (Map.Entry<String, Double> e : nearestByRoute.entrySet()) {
            if (e.getValue() < selectedDistance) { selectedDistance = e.getValue(); selectedRoute = e.getKey(); }
        }
        if (selectedRoute == null) return null;

        JSONArray geometries = new JSONArray();
        List<String> chosenShapes = routeShapes.get(selectedRoute);
        if (chosenShapes != null) for (String sid : chosenShapes) {
            List<ShapePoint> list = points.get(sid);
            if (list == null || list.size() < 2) continue;
            Collections.sort(list, Comparator.comparingInt(p -> p.sequence));
            JSONArray coords = new JSONArray();
            for (ShapePoint p : list) coords.put(new JSONArray().put(p.lon).put(p.lat));
            geometries.put(new JSONObject().put("direction", shapeDirection.get(sid)).put("coordinates", coords));
        }
        if (geometries.length() == 0) return null;

        JSONArray stops = loadStopsForShapes(zipFile, chosenShapes, shapeTrip, shapeDirection);
        String label = routeLabels.get(selectedRoute);
        if (label == null || label.trim().isEmpty()) label = requestedLine == null ? "" : requestedLine.trim();
        JSONObject out = new JSONObject();
        out.put("line", label);
        out.put("geometries", geometries);
        out.put("stops", stops);
        JSONObject timetable = loadUpcomingTimetable(zipFile, selectedRoute, queryLat, queryLon);
        if (timetable != null) out.put("timetable", timetable);
        out.put("distanceToRouteMetres", Math.round(selectedDistance));
        return out;
    }

    private static JSONObject loadUpcomingTimetable(File zipFile, String routeIdValue, double queryLat, double queryLon) {
        try {
            LocalDate today = LocalDate.now(ZoneId.of("Europe/London"));
            Set<String> activeServices = activeServiceIds(zipFile, today);
            boolean hasServiceCalendar = entryExists(zipFile, "calendar.txt") || entryExists(zipFile, "calendar_dates.txt");
            Map<String, TripInfo> trips = new HashMap<>();
            try (BufferedReader reader = entryReader(zipFile, "trips.txt")) {
                if (reader == null) return null;
                List<String> header = csv(reader.readLine());
                int routeId = indexOf(header, "route_id"), tripId = indexOf(header, "trip_id"), serviceId = indexOf(header, "service_id"), directionId = indexOf(header, "direction_id"), headsign = indexOf(header, "trip_headsign");
                String row;
                while ((row = reader.readLine()) != null) {
                    List<String> cols = csv(row); if (!routeIdValue.equals(value(cols, routeId))) continue;
                    String service = value(cols, serviceId); if (hasServiceCalendar && !activeServices.contains(service)) continue;
                    String trip = value(cols, tripId); if (trip.isEmpty()) continue;
                    String direction = "1".equals(value(cols, directionId)) ? "inbound" : "outbound";
                    trips.put(trip, new TripInfo(value(cols, headsign), direction));
                }
            }
            if (trips.isEmpty()) return null;

            List<DepartureRaw> departures = new ArrayList<>(); Set<String> stopIds = new HashSet<>();
            try (BufferedReader reader = entryReader(zipFile, "stop_times.txt")) {
                if (reader == null) return null;
                List<String> header = csv(reader.readLine()); int tripId = indexOf(header, "trip_id"), stopId = indexOf(header, "stop_id"), departure = indexOf(header, "departure_time");
                String row; while ((row = reader.readLine()) != null) {
                    List<String> cols = csv(row); String trip = value(cols, tripId); TripInfo info = trips.get(trip); if (info == null) continue;
                    String stop = value(cols, stopId), time = value(cols, departure); if (stop.isEmpty() || time.isEmpty()) continue;
                    departures.add(new DepartureRaw(stop, time, info.destination, info.direction)); stopIds.add(stop);
                }
            }
            if (departures.isEmpty()) return null;

            Map<String, StopInfo> stopInfo = new HashMap<>();
            try (BufferedReader reader = entryReader(zipFile, "stops.txt")) {
                if (reader == null) return null; List<String> header = csv(reader.readLine());
                int stopId = indexOf(header, "stop_id"), name = indexOf(header, "stop_name"), lat = indexOf(header, "stop_lat"), lon = indexOf(header, "stop_lon");
                String row; while ((row = reader.readLine()) != null) {
                    List<String> cols = csv(row); String id = value(cols, stopId); if (!stopIds.contains(id)) continue;
                    try { stopInfo.put(id, new StopInfo(value(cols, name), Double.parseDouble(value(cols, lat)), Double.parseDouble(value(cols, lon)))); } catch (Exception ignored) {}
                }
            }
            String nearest = null; double best = Double.POSITIVE_INFINITY;
            for (Map.Entry<String, StopInfo> e : stopInfo.entrySet()) { double d = approxDistanceMetres(queryLat, queryLon, e.getValue().lat, e.getValue().lon); if (d < best) { best = d; nearest = e.getKey(); } }
            if (nearest == null) return null;
            int now = LocalTime.now(ZoneId.of("Europe/London")).toSecondOfDay(); List<DepartureRaw> upcoming = new ArrayList<>();
            for (DepartureRaw d : departures) { if (!nearest.equals(d.stopId)) continue; int seconds = gtfsSeconds(d.time); if (seconds < 0) continue; int adjusted = seconds; while (adjusted < now - 60) adjusted += 86400; if (adjusted <= now + 6 * 3600) { d.sortSeconds = adjusted; upcoming.add(d); } }
            upcoming.sort(Comparator.comparingInt(d -> d.sortSeconds));
            JSONArray array = new JSONArray(); Set<String> dedupe = new HashSet<>();
            for (DepartureRaw d : upcoming) { String key = d.time + "|" + d.destination + "|" + d.direction; if (!dedupe.add(key)) continue; array.put(new JSONObject().put("time", displayGtfsTime(d.time)).put("destination", d.destination).put("direction", d.direction)); if (array.length() >= 12) break; }
            StopInfo si = stopInfo.get(nearest); JSONObject result = new JSONObject().put("stopId", nearest).put("stopName", si == null ? "Nearby stop" : si.name).put("departures", array).put("source", "BODS GTFS");
            return result;
        } catch (Exception ignored) { return null; }
    }

    private static Set<String> activeServiceIds(File zipFile, LocalDate date) {
        Set<String> active = new HashSet<>();
        try (BufferedReader reader = entryReader(zipFile, "calendar.txt")) {
            if (reader != null) { List<String> header = csv(reader.readLine()); int service = indexOf(header,"service_id"), start = indexOf(header,"start_date"), end = indexOf(header,"end_date"); String day = date.getDayOfWeek().name().toLowerCase(Locale.UK); int dayIndex = indexOf(header, day); String row; while((row=reader.readLine())!=null){List<String> c=csv(row); try{LocalDate a=LocalDate.parse(value(c,start),DateTimeFormatter.BASIC_ISO_DATE), b=LocalDate.parse(value(c,end),DateTimeFormatter.BASIC_ISO_DATE); if(!date.isBefore(a)&&!date.isAfter(b)&&"1".equals(value(c,dayIndex)))active.add(value(c,service));}catch(Exception ignored){}} }
        } catch (Exception ignored) {}
        try (BufferedReader reader = entryReader(zipFile, "calendar_dates.txt")) {
            if (reader != null) { List<String> header = csv(reader.readLine()); int service=indexOf(header,"service_id"), dateIdx=indexOf(header,"date"), type=indexOf(header,"exception_type"); String target=date.format(DateTimeFormatter.BASIC_ISO_DATE), row; while((row=reader.readLine())!=null){List<String> c=csv(row); if(!target.equals(value(c,dateIdx)))continue; if("1".equals(value(c,type)))active.add(value(c,service)); else if("2".equals(value(c,type)))active.remove(value(c,service));} }
        } catch (Exception ignored) {}
        return active;
    }

    private static int gtfsSeconds(String value) { try { String[] b=value.split(":"); if(b.length<2)return -1; return Integer.parseInt(b[0])*3600+Integer.parseInt(b[1])*60+(b.length>2?Integer.parseInt(b[2]):0); } catch(Exception e){return -1;} }
    private static String displayGtfsTime(String value) { int sec=gtfsSeconds(value); if(sec<0)return value; sec%=86400; return String.format(Locale.UK,"%02d:%02d",sec/3600,(sec%3600)/60); }

    private static JSONArray loadStopsForShapes(File zipFile, List<String> chosenShapes,
                                                     Map<String, String> shapeTrip,
                                                     Map<String, String> shapeDirection) throws Exception {
        JSONArray out = new JSONArray();
        if (chosenShapes == null || chosenShapes.isEmpty()) return out;
        Map<String, String> tripDirection = new HashMap<>();
        for (String sid : chosenShapes) {
            String trip = shapeTrip.get(sid);
            if (trip != null && !trip.isEmpty()) tripDirection.put(trip, shapeDirection.get(sid));
        }
        if (tripDirection.isEmpty()) return out;

        List<TripStop> ordered = new ArrayList<>();
        Set<String> stopIds = new HashSet<>();
        try (BufferedReader reader = entryReader(zipFile, "stop_times.txt")) {
            if (reader == null) return out;
            List<String> header = csv(reader.readLine());
            int tripId = indexOf(header, "trip_id");
            int stopId = indexOf(header, "stop_id");
            int sequence = indexOf(header, "stop_sequence");
            String row;
            while ((row = reader.readLine()) != null) {
                List<String> cols = csv(row);
                String trip = value(cols, tripId);
                if (!tripDirection.containsKey(trip)) continue;
                String stop = value(cols, stopId);
                if (stop.isEmpty()) continue;
                int seq = 0; try { seq = Integer.parseInt(value(cols, sequence)); } catch (Exception ignored) {}
                ordered.add(new TripStop(trip, stop, seq, tripDirection.get(trip)));
                stopIds.add(stop);
            }
        }
        if (stopIds.isEmpty()) return out;

        Map<String, StopInfo> info = new HashMap<>();
        try (BufferedReader reader = entryReader(zipFile, "stops.txt")) {
            if (reader == null) return out;
            List<String> header = csv(reader.readLine());
            int stopId = indexOf(header, "stop_id");
            int name = indexOf(header, "stop_name");
            int lat = indexOf(header, "stop_lat");
            int lon = indexOf(header, "stop_lon");
            String row;
            while ((row = reader.readLine()) != null) {
                List<String> cols = csv(row);
                String id = value(cols, stopId);
                if (!stopIds.contains(id)) continue;
                try {
                    info.put(id, new StopInfo(value(cols, name), Double.parseDouble(value(cols, lat)), Double.parseDouble(value(cols, lon))));
                } catch (Exception ignored) {}
            }
        }

        Collections.sort(ordered, (a, b) -> {
            int d = a.trip.compareTo(b.trip);
            return d != 0 ? d : Integer.compare(a.sequence, b.sequence);
        });
        Set<String> emitted = new HashSet<>();
        for (TripStop ts : ordered) {
            StopInfo si = info.get(ts.stopId);
            if (si == null) continue;
            String unique = ts.direction + "|" + ts.stopId;
            if (!emitted.add(unique)) continue;
            out.put(new JSONObject().put("id", ts.stopId).put("name", si.name.isEmpty() ? "Bus stop" : si.name)
                    .put("lat", si.lat).put("lon", si.lon).put("direction", ts.direction == null ? "" : ts.direction));
            if (out.length() >= 180) break;
        }
        return out;
    }

    private static boolean containsBothDirections(Map<String, String> directions) {
        boolean in = false, out = false;
        for (String d : directions.values()) {
            if ("inbound".equals(d)) in = true;
            if ("outbound".equals(d)) out = true;
        }
        return in && out;
    }

    private static String regionFor(double lat, double lon) {
        // DfT publishes these smaller regional GTFS downloads as well as the full GB feed.
        // The broad coordinate gates only choose which cache to download; the route itself is
        // subsequently chosen by distance to its actual GTFS geometry.
        if (lat >= 54.63) return "scotland";
        if (lat >= 51.25 && lat <= 53.55 && lon <= -2.65 && (lon <= -3.00 || lat >= 52.05)) return "wales";
        if (lat >= 54.10) return "north_east";
        if (lat >= 52.70 && lon <= -1.45) return "north_west";
        if (lat >= 52.05 && lon >= 0.20) return "east_anglia";
        if (lat >= 52.05 && lon > -1.45) return "east_midlands";
        if (lat < 52.20 && lon >= -1.15) return "south_east";
        if (lat < 52.20) return "south_west";
        // The public download set does not expose a dedicated West Midlands/Yorkshire file;
        // use the England feed for central areas rather than guessing the wrong region.
        return "england";
    }

    private static boolean routeMatches(String requested, String shortName, String longName) {
        String s = normaliseLine(shortName);
        if (requested.equals(s)) return true;
        // Long names sometimes include the public line number at the front (e.g. "75 Hengrove...").
        String l = normaliseLine(longName);
        return l.equals(requested) || l.startsWith(requested + " ") || l.startsWith(requested + "-");
    }

    private static String normaliseLine(String value) {
        if (value == null) return "";
        String v = value.trim().toLowerCase(Locale.UK);
        if (v.startsWith("bus ")) v = v.substring(4).trim();
        return v.replaceAll("\\s+", " ");
    }

    private static boolean entryExists(File zipFile, String wanted) {
        try (ZipInputStream zip = new ZipInputStream(new FileInputStream(zipFile), StandardCharsets.UTF_8)) {
            ZipEntry entry;
            String wantedLower = wanted.toLowerCase(Locale.UK);
            while ((entry = zip.getNextEntry()) != null) {
                String name = entry.getName();
                String lower = name.toLowerCase(Locale.UK);
                if (name.equalsIgnoreCase(wanted) || lower.endsWith("/" + wantedLower)) return true;
            }
        } catch (Exception ignored) {}
        return false;
    }

    private static BufferedReader entryReader(File zipFile, String wanted) throws Exception {
        ZipInputStream zip = new ZipInputStream(new FileInputStream(zipFile), StandardCharsets.UTF_8);
        ZipEntry entry;
        while ((entry = zip.getNextEntry()) != null) {
            String name = entry.getName();
            if (name.equalsIgnoreCase(wanted) || name.toLowerCase(Locale.UK).endsWith("/" + wanted.toLowerCase(Locale.UK))) {
                return new BufferedReader(new InputStreamReader(zip, StandardCharsets.UTF_8));
            }
        }
        zip.close();
        return null;
    }

    private static int indexOf(List<String> header, String name) {
        for (int i = 0; i < header.size(); i++) {
            String v = header.get(i).replace("\ufeff", "").trim();
            if (name.equalsIgnoreCase(v)) return i;
        }
        return -1;
    }

    private static String value(List<String> cols, int index) {
        return index >= 0 && index < cols.size() ? cols.get(index).trim() : "";
    }

    private static List<String> csv(String line) {
        List<String> out = new ArrayList<>();
        if (line == null) return out;
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '"') {
                if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') { cell.append('"'); i++; }
                else quoted = !quoted;
            } else if (c == ',' && !quoted) {
                out.add(cell.toString()); cell.setLength(0);
            } else cell.append(c);
        }
        out.add(cell.toString());
        return out;
    }

    private static void download(String url, File destination) throws Exception {
        HttpURLConnection connection = (HttpURLConnection)new URL(url).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(60000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("Accept", "application/zip, application/octet-stream, */*");
        connection.setRequestProperty("User-Agent", "OpenRoad-Android/0.6.27");
        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) {
            connection.disconnect();
            throw new Exception("BODS GTFS returned HTTP " + status);
        }
        try (InputStream in = connection.getInputStream(); FileOutputStream out = new FileOutputStream(destination)) {
            byte[] buffer = new byte[32768];
            int n;
            while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
        } finally { connection.disconnect(); }
    }

    private static void copy(File source, File destination) throws Exception {
        try (InputStream in = new FileInputStream(source); FileOutputStream out = new FileOutputStream(destination)) {
            byte[] buffer = new byte[32768]; int n;
            while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
        }
    }

    private static double approxDistanceMetres(double lat1, double lon1, double lat2, double lon2) {
        double x = Math.toRadians(lon2 - lon1) * Math.cos(Math.toRadians((lat1 + lat2) / 2.0));
        double y = Math.toRadians(lat2 - lat1);
        return Math.sqrt(x * x + y * y) * 6371000.0;
    }

    private static final class TripInfo { final String destination; final String direction; TripInfo(String destination,String direction){this.destination=destination==null?"":destination;this.direction=direction==null?"":direction;} }
    private static final class DepartureRaw { final String stopId; final String time; final String destination; final String direction; int sortSeconds; DepartureRaw(String stopId,String time,String destination,String direction){this.stopId=stopId;this.time=time;this.destination=destination==null?"":destination;this.direction=direction==null?"":direction;} }

    private static final class TripStop {
        final String trip; final String stopId; final int sequence; final String direction;
        TripStop(String trip, String stopId, int sequence, String direction) {
            this.trip = trip; this.stopId = stopId; this.sequence = sequence; this.direction = direction;
        }
    }

    private static final class StopInfo {
        final String name; final double lat; final double lon;
        StopInfo(String name, double lat, double lon) { this.name = name == null ? "" : name; this.lat = lat; this.lon = lon; }
    }

    private static final class ShapePoint {
        final int sequence; final double lat; final double lon;
        ShapePoint(int sequence, double lat, double lon) { this.sequence = sequence; this.lat = lat; this.lon = lon; }
    }
}
