package uk.co.bengoodman.clearroute;

import android.location.Location;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Geometry/progress helpers used by the navigation service. */
public final class RouteMath {
    private static final double EARTH_RADIUS_METRES = 6371000.0;

    public static final class Point {
        final double lat;
        final double lon;
        Point(double lat, double lon) { this.lat = lat; this.lon = lon; }
    }

    public static final class Instruction {
        final int pointIndex;
        final String message;
        final String maneuver;
        final String instructionType;
        final double routeOffsetMetres;
        final long travelTimeSeconds;
        final double earlyAnnouncementOffsetMetres;
        final double mainAnnouncementOffsetMetres;

        Instruction(int pointIndex, String message, String maneuver, String instructionType,
                    double routeOffsetMetres, long travelTimeSeconds,
                    double earlyAnnouncementOffsetMetres, double mainAnnouncementOffsetMetres) {
            this.pointIndex = pointIndex;
            this.message = message;
            this.maneuver = maneuver;
            this.instructionType = instructionType;
            this.routeOffsetMetres = routeOffsetMetres;
            this.travelTimeSeconds = travelTimeSeconds;
            this.earlyAnnouncementOffsetMetres = earlyAnnouncementOffsetMetres;
            this.mainAnnouncementOffsetMetres = mainAnnouncementOffsetMetres;
        }
    }

    public static final class SpeedLimitSection {
        final double startOffsetMetres;
        final double endOffsetMetres;
        final int speedLimitKmh;

        SpeedLimitSection(double startOffsetMetres, double endOffsetMetres, int speedLimitKmh) {
            this.startOffsetMetres = startOffsetMetres;
            this.endOffsetMetres = endOffsetMetres;
            this.speedLimitKmh = speedLimitKmh;
        }
    }

    public static final class ParsedRoute {
        final List<Point> points = new ArrayList<>();
        final List<Instruction> instructions = new ArrayList<>();
        final List<SpeedLimitSection> speedLimits = new ArrayList<>();
        double[] cumulative;
        double geometryDistance;
        double totalDistance;
        long totalTravelSeconds;
    }

    public static final class Projection {
        final int segmentIndex;
        final double segmentFraction;
        final double routeOffsetMetres;
        final double offRouteMetres;
        final float routeBearingDegrees;

        Projection(int segmentIndex, double segmentFraction, double routeOffsetMetres,
                   double offRouteMetres, float routeBearingDegrees) {
            this.segmentIndex = segmentIndex;
            this.segmentFraction = segmentFraction;
            this.routeOffsetMetres = routeOffsetMetres;
            this.offRouteMetres = offRouteMetres;
            this.routeBearingDegrees = routeBearingDegrees;
        }
    }

    private RouteMath() {}

    public static ParsedRoute parse(String responseJson, int routeIndex) throws Exception {
        JSONObject root = new JSONObject(responseJson);
        JSONArray routes = root.getJSONArray("routes");
        if (routes.length() == 0) throw new Exception("Route response contained no routes");
        JSONObject route = routes.getJSONObject(Math.max(0, Math.min(routeIndex, routes.length() - 1)));
        ParsedRoute parsed = new ParsedRoute();

        JSONObject summary = route.optJSONObject("summary");
        if (summary != null) {
            parsed.totalDistance = summary.optDouble("lengthInMeters", 0);
            parsed.totalTravelSeconds = summary.optLong("travelTimeInSeconds", 0);
        }

        JSONArray legs = route.optJSONArray("legs");
        if (legs != null) {
            for (int l = 0; l < legs.length(); l++) {
                JSONObject leg = legs.optJSONObject(l);
                JSONArray pts = leg == null ? null : leg.optJSONArray("points");
                if (pts == null) continue;
                for (int i = 0; i < pts.length(); i++) {
                    JSONObject p = pts.optJSONObject(i);
                    if (p == null) continue;
                    parsed.points.add(new Point(p.optDouble("latitude"), p.optDouble("longitude")));
                }
            }
        }

        parsed.cumulative = new double[parsed.points.size()];
        for (int i = 1; i < parsed.points.size(); i++) {
            Point a = parsed.points.get(i - 1), b = parsed.points.get(i);
            parsed.cumulative[i] = parsed.cumulative[i - 1] + distance(a.lat, a.lon, b.lat, b.lon);
        }
        parsed.geometryDistance = parsed.cumulative.length == 0 ? 0 : parsed.cumulative[parsed.cumulative.length - 1];
        if (parsed.totalDistance <= 0) parsed.totalDistance = parsed.geometryDistance;

        // Legal speed limits are returned as route sections when requested from TomTom.
        // Convert their point-index ranges into route offsets once, so navigation can
        // display the limit for the driver's current progress without another API call.
        JSONArray sections = route.optJSONArray("sections");
        if (sections != null) {
            for (int i = 0; i < sections.length(); i++) {
                JSONObject section = sections.optJSONObject(i);
                if (section == null || !"SPEED_LIMIT".equals(section.optString("sectionType"))) continue;
                int kmh = section.optInt("maxSpeedLimitInKmh",
                        section.optInt("speedLimitInKmh",
                                section.optInt("maxSpeedLimitInKilometersPerHour", -1)));
                if (kmh <= 0) continue;
                int startIndex = clampPointIndex(parsed, section.optInt("startPointIndex", 0));
                int endIndex = clampPointIndex(parsed, section.optInt("endPointIndex", startIndex));
                double startOffset = cumulativeAt(parsed, Math.min(startIndex, endIndex));
                double endOffset = cumulativeAt(parsed, Math.max(startIndex, endIndex));
                if (endOffset < startOffset) {
                    double t = startOffset; startOffset = endOffset; endOffset = t;
                }
                parsed.speedLimits.add(new SpeedLimitSection(startOffset, endOffset, kmh));
            }
        }

        JSONObject guidance = route.optJSONObject("guidance");
        JSONArray instructions = guidance == null ? null : guidance.optJSONArray("instructions");
        if (instructions != null) {
            for (int i = 0; i < instructions.length(); i++) {
                JSONObject ins = instructions.optJSONObject(i);
                if (ins == null) continue;
                int pointIndex = clampPointIndex(parsed, ins.optInt("pointIndex", 0));
                double routeOffset = ins.has("routeOffsetInMeters")
                        ? ins.optDouble("routeOffsetInMeters", cumulativeAt(parsed, pointIndex))
                        : cumulativeAt(parsed, pointIndex);
                long travelTime = ins.optLong("travelTimeInSeconds", -1L);
                double earlyOffset = announcementOffset(parsed, ins.optJSONObject("earlyWarningAnnouncement"), routeOffset);
                double mainOffset = announcementOffset(parsed, ins.optJSONObject("mainAnnouncement"), routeOffset);
                parsed.instructions.add(new Instruction(
                        pointIndex,
                        ins.optString("message", "Continue"),
                        ins.optString("maneuver", ""),
                        ins.optString("instructionType", ""),
                        routeOffset,
                        travelTime,
                        earlyOffset,
                        mainOffset));
            }
        }
        return parsed;
    }

    private static int clampPointIndex(ParsedRoute route, int index) {
        if (route.points.isEmpty()) return 0;
        return Math.max(0, Math.min(index, route.points.size() - 1));
    }

    private static double cumulativeAt(ParsedRoute route, int index) {
        if (route.cumulative == null || route.cumulative.length == 0) return 0;
        return route.cumulative[Math.max(0, Math.min(index, route.cumulative.length - 1))];
    }

    private static double announcementOffset(ParsedRoute route, JSONObject announcement, double maneuverOffset) {
        if (announcement == null) return -1;
        int pointIndex = announcement.optInt("pointIndex", -1);
        if (pointIndex >= 0 && pointIndex < route.points.size()) return cumulativeAt(route, pointIndex);
        double distance = announcement.optDouble("distanceInMeters", -1);
        return distance >= 0 ? Math.max(0, maneuverOffset - distance) : -1;
    }

    /**
     * Projects a location onto the route. When a previous segment is known we search a
     * generous window around it first, which avoids snapping to a distant future branch
     * when a route crosses itself. If that local window is clearly wrong we fall back to
     * a full-route search.
     */
    public static Projection project(ParsedRoute route, double lat, double lon, int hintSegment) {
        if (route == null || route.points.isEmpty()) {
            return new Projection(0, 0, 0, Double.MAX_VALUE, 0f);
        }
        if (route.points.size() == 1) {
            Point only = route.points.get(0);
            return new Projection(0, 0, 0, distance(lat, lon, only.lat, only.lon), 0f);
        }

        Projection local = null;
        if (hintSegment >= 0) {
            int from = Math.max(0, hintSegment - 120);
            int to = Math.min(route.points.size() - 2, hintSegment + 220);
            local = projectRange(route, lat, lon, from, to);
            if (local.offRouteMetres <= 180) return local;
        }
        return projectRange(route, lat, lon, 0, route.points.size() - 2);
    }

    public static Projection project(ParsedRoute route, double lat, double lon) {
        return project(route, lat, lon, -1);
    }

    private static Projection projectRange(ParsedRoute route, double lat, double lon, int from, int to) {
        double latRad = Math.toRadians(lat);
        double cosLat = Math.max(0.2, Math.cos(latRad));
        double bestOff = Double.MAX_VALUE;
        int bestSegment = Math.max(0, from);
        double bestFraction = 0;

        for (int i = Math.max(0, from); i <= Math.min(route.points.size() - 2, to); i++) {
            Point a = route.points.get(i), b = route.points.get(i + 1);
            double ax = Math.toRadians(a.lon - lon) * cosLat * EARTH_RADIUS_METRES;
            double ay = Math.toRadians(a.lat - lat) * EARTH_RADIUS_METRES;
            double bx = Math.toRadians(b.lon - lon) * cosLat * EARTH_RADIUS_METRES;
            double by = Math.toRadians(b.lat - lat) * EARTH_RADIUS_METRES;
            double vx = bx - ax, vy = by - ay;
            double vv = vx * vx + vy * vy;
            double t = vv < 0.0001 ? 0 : -(ax * vx + ay * vy) / vv;
            t = Math.max(0, Math.min(1, t));
            double qx = ax + t * vx, qy = ay + t * vy;
            double off = Math.hypot(qx, qy);
            if (off < bestOff) {
                bestOff = off;
                bestSegment = i;
                bestFraction = t;
            }
        }

        double start = cumulativeAt(route, bestSegment);
        double end = cumulativeAt(route, bestSegment + 1);
        double offset = start + (end - start) * bestFraction;
        Point a = route.points.get(bestSegment), b = route.points.get(bestSegment + 1);
        float bearing = bearing(a.lat, a.lon, b.lat, b.lon);
        return new Projection(bestSegment, bestFraction, offset, bestOff, bearing);
    }

    public static Instruction nextInstruction(ParsedRoute route, double progressOffsetMetres) {
        if (route == null) return null;
        // Small tolerance prevents GPS projection jitter around the exact manoeuvre point
        // from repeatedly switching backwards to an instruction just completed.
        double threshold = Math.max(0, progressOffsetMetres - 8.0);
        for (Instruction instruction : route.instructions) {
            if (instruction.routeOffsetMetres >= threshold) return instruction;
        }
        return null;
    }

    public static double distanceToInstruction(Instruction instruction, double progressOffsetMetres) {
        return instruction == null ? 0 : Math.max(0, instruction.routeOffsetMetres - progressOffsetMetres);
    }

    public static double remainingDistance(ParsedRoute route, double progressOffsetMetres) {
        if (route == null) return 0;
        double total = route.totalDistance > 0 ? route.totalDistance : route.geometryDistance;
        return Math.max(0, total - progressOffsetMetres);
    }

    /** Estimate remaining route time using TomTom's cumulative instruction times. */
    public static long remainingTravelSeconds(ParsedRoute route, double progressOffsetMetres) {
        if (route == null || route.totalTravelSeconds <= 0) return 0;
        double totalDistance = route.totalDistance > 0 ? route.totalDistance : route.geometryDistance;
        if (totalDistance <= 0) return 0;

        double progress = Math.max(0, Math.min(progressOffsetMetres, totalDistance));
        double prevOffset = 0;
        long prevTime = 0;
        for (Instruction instruction : route.instructions) {
            if (instruction.travelTimeSeconds < 0 || instruction.routeOffsetMetres < prevOffset) continue;
            double nextOffset = Math.min(totalDistance, instruction.routeOffsetMetres);
            long nextTime = Math.min(route.totalTravelSeconds, instruction.travelTimeSeconds);
            if (progress <= nextOffset) {
                double span = Math.max(1.0, nextOffset - prevOffset);
                double fraction = Math.max(0, Math.min(1, (progress - prevOffset) / span));
                long elapsed = Math.round(prevTime + (nextTime - prevTime) * fraction);
                return Math.max(0, route.totalTravelSeconds - elapsed);
            }
            prevOffset = nextOffset;
            prevTime = nextTime;
        }

        double span = Math.max(1.0, totalDistance - prevOffset);
        double fraction = Math.max(0, Math.min(1, (progress - prevOffset) / span));
        long elapsed = Math.round(prevTime + (route.totalTravelSeconds - prevTime) * fraction);
        return Math.max(0, route.totalTravelSeconds - elapsed);
    }

    public static int speedLimitKmhAt(ParsedRoute route, double progressOffsetMetres) {
        if (route == null || route.speedLimits.isEmpty()) return -1;
        double p = Math.max(0, progressOffsetMetres);
        for (SpeedLimitSection section : route.speedLimits) {
            if (p + 3 >= section.startOffsetMetres && p <= section.endOffsetMetres + 3) {
                return section.speedLimitKmh;
            }
        }
        return -1;
    }

    /** Return the interpolated route point at a distance from the start. */
    public static Point pointAtOffset(ParsedRoute route, double offsetMetres) {
        if (route == null || route.points.isEmpty()) return null;
        if (route.points.size() == 1 || route.cumulative == null || route.cumulative.length < 2) return route.points.get(0);
        double target = Math.max(0, Math.min(offsetMetres, route.geometryDistance));
        for (int i = 0; i < route.cumulative.length - 1; i++) {
            double aOffset = route.cumulative[i], bOffset = route.cumulative[i + 1];
            if (target > bOffset && i < route.cumulative.length - 2) continue;
            double span = Math.max(0.001, bOffset - aOffset);
            double f = Math.max(0, Math.min(1, (target - aOffset) / span));
            Point a = route.points.get(i), b = route.points.get(i + 1);
            return new Point(a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f);
        }
        return route.points.get(route.points.size() - 1);
    }

    public static double distance(double lat1, double lon1, double lat2, double lon2) {
        float[] result = new float[1];
        Location.distanceBetween(lat1, lon1, lat2, lon2, result);
        return result[0];
    }

    public static float bearing(double lat1, double lon1, double lat2, double lon2) {
        float[] result = new float[3];
        Location.distanceBetween(lat1, lon1, lat2, lon2, result);
        float value = result.length > 1 ? result[1] : 0f;
        return value < 0 ? value + 360f : value;
    }
}
