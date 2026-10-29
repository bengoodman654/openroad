package uk.co.bengoodman.clearroute;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.media.AudioAttributes;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.util.Log;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import org.json.JSONObject;

import java.util.Locale;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Foreground turn-by-turn navigation service. */
public class NavigationService extends Service implements LocationListener, TextToSpeech.OnInitListener {
    public static final String ACTION_UPDATE = "uk.co.bengoodman.clearroute.NAV_UPDATE";
    public static final String ACTION_ROUTE_UPDATED = "uk.co.bengoodman.clearroute.ROUTE_UPDATED";
    public static final String ACTION_STOPPED = "uk.co.bengoodman.clearroute.NAV_STOPPED";
    public static final String ACTION_STOP = "uk.co.bengoodman.clearroute.STOP_NAV";
    public static final String ACTION_FORCE_REROUTE = "uk.co.bengoodman.clearroute.FORCE_REROUTE";
    public static final String ACTION_AVOID_AHEAD = "uk.co.bengoodman.clearroute.AVOID_AHEAD";
    public static final String ACTION_RELOAD_ROUTE = "uk.co.bengoodman.clearroute.RELOAD_ROUTE";
    public static final String ACTION_STATUS = "uk.co.bengoodman.clearroute.NAV_STATUS";

    private static final String CHANNEL_ID = "clearroute_navigation";
    private static final int NOTIFICATION_ID = 7401;
    private static final long MIN_LOCATION_PROCESS_INTERVAL_MS = 700L;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private LocationManager locationManager;
    private FusedLocationProviderClient fusedLocationClient;
    private LocationCallback fusedLocationCallback;
    private TextToSpeech tts;
    private String configuredTtsEngine = "";
    private boolean triedTtsFallback = false;
    private volatile boolean ttsReady = false;

    private RouteMath.ParsedRoute route;
    private double destLat, destLon;
    private String mode = "drive";
    private int routeIndex = 0;
    private boolean hasWaypoint = false;
    private double waypointLat = 0, waypointLon = 0;
    private String waypointName = "Stop";

    private int offRouteHits = 0;
    private long lastReroute = 0;
    private boolean rerouting = false;
    private String activeInstructionKey = "";
    private boolean announcedEarly = false;
    private boolean announcedNear = false;
    private int lastSegmentIndex = -1;
    private double lastProgressOffset = 0;
    private long lastProcessedLocationElapsed = 0;
    private boolean platformFallbackStarted = false;
    private Location lastAcceptedLocation;
    private Location lastRawLocation;
    private float smoothedSpeedMps = 0f;
    private boolean hasSmoothedSpeed = false;
    private final List<ApiClient.AvoidBox> sessionAvoidAreas = new ArrayList<>();

    @Override public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        if ("voice".equals(navigationAlertMode())) initialiseTts();

        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
        fusedLocationCallback = new LocationCallback() {
            @Override public void onLocationResult(LocationResult result) {
                if (result == null) return;
                Location location = result.getLastLocation();
                if (location != null) handleLocation(location);
            }
        };
    }

    private void initialiseTts() {
        ttsReady = false;
        configuredTtsEngine = getSharedPreferences("clearroute_local", MODE_PRIVATE).getString("tts_engine", "");
        if (configuredTtsEngine == null) configuredTtsEngine = "";
        try {
            tts = configuredTtsEngine.trim().isEmpty()
                    ? new TextToSpeech(this, this)
                    : new TextToSpeech(this, this, configuredTtsEngine.trim());
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not create selected TTS engine", e);
            configuredTtsEngine = "";
            try { tts = new TextToSpeech(this, this); } catch (Exception ignored) {}
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopNavigation("stopped");
            return START_NOT_STICKY;
        }
        if (intent != null && ACTION_FORCE_REROUTE.equals(intent.getAction())) {
            forceReroute(false);
            return START_STICKY;
        }
        if (intent != null && ACTION_AVOID_AHEAD.equals(intent.getAction())) {
            forceReroute(true);
            return START_STICKY;
        }
        if (intent != null && ACTION_RELOAD_ROUTE.equals(intent.getAction())) {
            try {
                loadRoute();
                lastSegmentIndex = -1;
                lastProgressOffset = 0;
                activeInstructionKey = "";
                announcedEarly = false;
                announcedNear = false;
                offRouteHits = 0;
                sendBroadcast(new Intent(ACTION_ROUTE_UPDATED).setPackage(getPackageName()));
                sendStatus(hasWaypoint ? "Stop added to route." : "Route updated.");
            } catch (Exception e) {
                Log.w("ClearRouteNavigation", "Could not reload active route", e);
                sendStatus("Could not update the route.");
            }
            return START_STICKY;
        }

        if (intent != null) {
            destLat = intent.getDoubleExtra("destLat", 0);
            destLon = intent.getDoubleExtra("destLon", 0);
            mode = normaliseMode(intent.getStringExtra("mode"));
            routeIndex = intent.getIntExtra("routeIndex", 0);
        }

        startForeground(NOTIFICATION_ID, notification("Starting navigation", "Finding your position"));
        try { loadRoute(); } catch (Exception e) { Log.w("ClearRouteNavigation", "Could not restore active route", e); }
        if (route == null || route.points.isEmpty()) {
            stopNavigation("error");
            return START_NOT_STICKY;
        }

        requestLocationUpdates();
        return START_STICKY;
    }

    private static String normaliseMode(String value) {
        return "cycle".equals(value) || "walk".equals(value) ? value : "drive";
    }

    private boolean enhancedLocationEnabled() {
        return getSharedPreferences("clearroute_local", MODE_PRIVATE).getBoolean("enhanced_location", true);
    }

    /**
     * Keep a single high-frequency location owner while navigating. Fused Location is
     * primary when enabled; framework GPS/network are used only as fallback or when the
     * user deliberately disables enhanced location.
     */
    private void requestLocationUpdates() {
        stopLocationUpdates();
        platformFallbackStarted = false;
        if (!hasLocationPermission()) return;

        if (enhancedLocationEnabled() && fusedLocationClient != null) {
            try {
                LocationRequest request = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1000L)
                        .setMinUpdateIntervalMillis(750L)
                        .setWaitForAccurateLocation(false)
                        .build();
                fusedLocationClient.requestLocationUpdates(request, fusedLocationCallback, Looper.getMainLooper())
                        .addOnFailureListener(e -> {
                            Log.w("ClearRouteLocation", "Navigation fused location failed; using Android providers", e);
                            startPlatformLocationUpdates();
                        });
                return;
            } catch (Exception e) {
                Log.w("ClearRouteLocation", "Navigation fused location unavailable; using Android providers", e);
            }
        }
        startPlatformLocationUpdates();
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void startPlatformLocationUpdates() {
        if (platformFallbackStarted || !hasLocationPermission() || locationManager == null) return;
        platformFallbackStarted = true;
        try {
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1500L, 1f, this, Looper.getMainLooper());
            }
        } catch (Exception e) {
            Log.w("ClearRouteLocation", "Navigation network location failed", e);
        }
        try {
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 1f, this, Looper.getMainLooper());
            }
        } catch (Exception e) {
            Log.w("ClearRouteLocation", "Navigation GPS location failed", e);
        }
    }

    @Override public void onLocationChanged(Location location) {
        handleLocation(location);
    }

    private void handleLocation(Location location) {
        if (location == null || route == null || route.points.isEmpty()) return;
        lastRawLocation = new Location(location);
        if (!isPlausibleLocation(location)) return;

        long nowElapsed = SystemClock.elapsedRealtime();
        if (nowElapsed - lastProcessedLocationElapsed < MIN_LOCATION_PROCESS_INTERVAL_MS) return;
        lastProcessedLocationElapsed = nowElapsed;
        lastAcceptedLocation = new Location(location);

        RouteMath.Projection projection = RouteMath.project(route, location.getLatitude(), location.getLongitude(), lastSegmentIndex);
        lastSegmentIndex = projection.segmentIndex;

        // Navigation progress should not jump backwards because of GPS jitter around a
        // junction or a route that crosses itself.
        double progress = Math.max(lastProgressOffset, projection.routeOffsetMetres);
        lastProgressOffset = progress;

        if (hasWaypoint) {
            double toWaypoint = RouteMath.distance(location.getLatitude(), location.getLongitude(), waypointLat, waypointLon);
            double reachedThreshold = "walk".equals(mode) ? 35.0 : ("cycle".equals(mode) ? 45.0 : 75.0);
            if (toWaypoint <= reachedThreshold) {
                hasWaypoint = false;
                try {
                    JSONObject state = ActiveRouteStore.load(this);
                    if (state != null) {
                        state.remove("hasWaypoint");
                        state.remove("waypointLat");
                        state.remove("waypointLon");
                        state.remove("waypointName");
                        ActiveRouteStore.save(this, state);
                    }
                } catch (Exception ignored) {}
            }
        }

        double remaining = RouteMath.remainingDistance(route, progress);
        long remainingSeconds = RouteMath.remainingTravelSeconds(route, progress);
        RouteMath.Instruction next = RouteMath.nextInstruction(route, progress);
        double nextDistance = RouteMath.distanceToInstruction(next, progress);

        evaluateOffRoute(location, projection.offRouteMetres);

        float rawSpeed = location.hasSpeed() ? Math.max(0f, location.getSpeed()) : 0f;
        float displaySpeed = smoothSpeed(rawSpeed);
        int speedLimitKmh = "drive".equals(mode) ? RouteMath.speedLimitKmhAt(route, progress) : -1;

        String alertPhase = next == null ? null : maybeAlert(next, nextDistance, progress, displaySpeed);
        String title = next == null ? "Continue to destination" : next.message;
        String detail = formatDistance(next == null ? remaining : nextDistance) + " • " + formatTime(remainingSeconds) + " remaining";
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(NOTIFICATION_ID, notification(title, detail));

        float displayBearing = chooseDisplayBearing(location, projection.routeBearingDegrees);
        boolean hasDisplayBearing = route.points.size() > 1;

        // Keep the display marker visually attached to the route while GPS is merely
        // noisy, but retain the raw fix for off-route detection/rerouting. This prevents
        // brief rural fixes from throwing the blue marker across the map.
        double snapThreshold = Math.max("walk".equals(mode) ? 20 : ("cycle".equals(mode) ? 30 : 45),
                location.hasAccuracy() ? location.getAccuracy() * 1.35 : 0);
        double displayLat = location.getLatitude();
        double displayLon = location.getLongitude();
        if (projection.offRouteMetres <= Math.min(110, snapThreshold)) {
            RouteMath.Point snapped = RouteMath.pointAtOffset(route, progress);
            if (snapped != null) { displayLat = snapped.lat; displayLon = snapped.lon; }
        }

        Intent update = new Intent(ACTION_UPDATE).setPackage(getPackageName());
        update.putExtra("lat", displayLat);
        update.putExtra("lon", displayLon);
        update.putExtra("bearing", displayBearing);
        update.putExtra("hasBearing", hasDisplayBearing);
        update.putExtra("speed", displaySpeed);
        update.putExtra("speedLimitKmh", speedLimitKmh);
        update.putExtra("instruction", title);
        update.putExtra("maneuver", next == null ? "" : next.maneuver);
        update.putExtra("instructionDistance", next == null ? remaining : nextDistance);
        update.putExtra("remainingDistance", remaining);
        update.putExtra("remainingSeconds", remainingSeconds);
        if (alertPhase != null && "flash".equals(navigationAlertMode())) {
            update.putExtra("visualAlert", true);
            update.putExtra("alertPhase", alertPhase);
        }
        sendBroadcast(update);

        double straightToDestination = RouteMath.distance(location.getLatitude(), location.getLongitude(), destLat, destLon);
        if ((remaining < 28 || straightToDestination < 25) && projection.offRouteMetres < 80) {
            if ("voice".equals(navigationAlertMode())) speakNavigation("You have arrived", "arrived");
            stopNavigation("arrived");
        }
    }

    private boolean isPlausibleLocation(Location candidate) {
        if (candidate == null) return false;
        float accuracy = candidate.hasAccuracy() ? candidate.getAccuracy() : 999f;
        Location previous = lastAcceptedLocation;
        if (previous == null) return accuracy <= 180f;

        long dtMs = Math.max(1L, candidate.getElapsedRealtimeNanos() > 0 && previous.getElapsedRealtimeNanos() > 0
                ? (candidate.getElapsedRealtimeNanos() - previous.getElapsedRealtimeNanos()) / 1_000_000L
                : candidate.getTime() - previous.getTime());
        if (dtMs < 0) return false;
        if (accuracy > 140f && dtMs < 12000L) return false;

        float jump = previous.distanceTo(candidate);
        double dt = Math.max(0.25, dtMs / 1000.0);
        float reportedSpeed = candidate.hasSpeed() ? Math.max(0f, candidate.getSpeed()) : 0f;
        float oldSpeed = previous.hasSpeed() ? Math.max(0f, previous.getSpeed()) : 0f;
        double plausible = Math.max(120.0, Math.max(accuracy * 2.5, (Math.max(reportedSpeed, oldSpeed) + 28.0) * dt));
        if (dtMs < 8000L && jump > plausible) {
            Log.d("ClearRouteLocation", "Ignored implausible navigation location jump");
            return false;
        }
        return true;
    }

    private float smoothSpeed(float value) {
        if (!hasSmoothedSpeed) {
            smoothedSpeedMps = value;
            hasSmoothedSpeed = true;
        } else {
            float alpha = value < 0.7f ? 0.55f : 0.35f;
            smoothedSpeedMps = alpha * value + (1f - alpha) * smoothedSpeedMps;
            if (value < 0.35f && smoothedSpeedMps < 0.8f) smoothedSpeedMps = 0f;
        }
        return Math.max(0f, smoothedSpeedMps);
    }

    private float chooseDisplayBearing(Location location, float routeBearing) {
        float speed = location.hasSpeed() ? location.getSpeed() : 0f;
        float threshold = "walk".equals(mode) ? 0.8f : ("cycle".equals(mode) ? 1.5f : 2.5f);
        if (location.hasBearing() && speed >= threshold) {
            float bearing = location.getBearing();
            return bearing < 0 ? bearing + 360f : bearing;
        }
        return routeBearing;
    }

    private void evaluateOffRoute(Location location, double offRouteMetres) {
        double base = "walk".equals(mode) ? 30 : ("cycle".equals(mode) ? 45 : 70);
        double accuracy = location.hasAccuracy() ? Math.max(0, location.getAccuracy()) : 0;
        double threshold = Math.max(base, accuracy * 1.7);

        // Very poor fixes should not trigger rerouting at all.
        if (accuracy > 120) {
            offRouteHits = 0;
            return;
        }

        if (offRouteMetres > threshold) offRouteHits++; else offRouteHits = 0;
        if (offRouteHits >= 4 && !rerouting && System.currentTimeMillis() - lastReroute > 30000) {
            lastReroute = System.currentTimeMillis();
            offRouteHits = 0;
            reroute(location.getLatitude(), location.getLongitude());
        }
    }

    private String navigationAlertMode() {
        String value = getSharedPreferences("clearroute_local", MODE_PRIVATE).getString("navigation_alert_mode", "voice");
        return ("flash".equals(value) || "silent".equals(value)) ? value : "voice";
    }

    /** Returns "early" or "near" when a visual alert should be emitted. */
    private String maybeAlert(RouteMath.Instruction instruction, double distance, double progressOffset, float speedMps) {
        String key = instruction.routeOffsetMetres + "|" + instruction.maneuver + "|" + instruction.message;
        if (!key.equals(activeInstructionKey)) {
            activeInstructionKey = key;
            announcedEarly = false;
            announcedNear = false;
        }

        double fallbackEarlyDistance = "walk".equals(mode) ? 80 : (speedMps > 16 ? 500 : (speedMps > 8 ? 300 : 140));
        double fallbackNearDistance = "walk".equals(mode) ? 30 : 65;
        boolean atEarlyPoint = instruction.earlyAnnouncementOffsetMetres >= 0
                ? progressOffset >= instruction.earlyAnnouncementOffsetMetres
                : distance <= fallbackEarlyDistance;
        boolean atMainPoint = instruction.mainAnnouncementOffsetMetres >= 0
                ? progressOffset >= instruction.mainAnnouncementOffsetMetres
                : distance <= fallbackNearDistance;
        String alertMode = navigationAlertMode();

        if (!announcedNear && atMainPoint) {
            if ("voice".equals(alertMode)) {
                // A TextToSpeech object exists before its engine is ready. Android explicitly
                // requires waiting for OnInit; if it is not ready yet, retry on the next GPS fix
                // rather than falsely recording this instruction as spoken.
                if (!speakNavigation(instruction.message, "near")) return null;
            }
            announcedNear = true;
            announcedEarly = true;
            return "flash".equals(alertMode) ? "near" : null;
        }

        if (!announcedEarly && atEarlyPoint) {
            if ("voice".equals(alertMode)) {
                if (!speakNavigation("In " + spokenDistance(distance) + ", " + instruction.message, "early")) return null;
            }
            announcedEarly = true;
            return "flash".equals(alertMode) ? "early" : null;
        }
        return null;
    }

    private boolean speakNavigation(String text, String utteranceId) {
        if (tts == null || !ttsReady || text == null || text.trim().isEmpty()) return false;
        try {
            int result = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId);
            if (result != TextToSpeech.SUCCESS) {
                Log.w("ClearRouteTTS", "Navigation speech request was rejected: " + utteranceId);
                return false;
            }
            return true;
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Navigation speech request failed", e);
            return false;
        }
    }

    private void reroute(double lat, double lon) {
        reroute(lat, lon, false);
    }

    private void forceReroute(boolean avoidAhead) {
        Location location = lastRawLocation != null ? lastRawLocation : lastAcceptedLocation;
        if (route == null || route.points.isEmpty() || location == null) {
            sendStatus("Waiting for a reliable location before rerouting.");
            return;
        }
        if (avoidAhead) {
            addAvoidAreaAhead();
            sendStatus("Avoiding the road ahead and finding a new route…");
        } else {
            sendStatus("Finding a fresh route…");
        }
        reroute(location.getLatitude(), location.getLongitude(), true);
    }

    private void addAvoidAreaAhead() {
        if (route == null || route.points.isEmpty()) return;
        double forward = "walk".equals(mode) ? 35.0 : ("cycle".equals(mode) ? 55.0 : 95.0);
        double radius = "walk".equals(mode) ? 22.0 : ("cycle".equals(mode) ? 28.0 : 45.0);
        RouteMath.Point point = RouteMath.pointAtOffset(route, Math.min(route.geometryDistance, lastProgressOffset + forward));
        if (point == null) return;
        double latDelta = radius / 111320.0;
        double cos = Math.max(0.25, Math.cos(Math.toRadians(point.lat)));
        double lonDelta = radius / (111320.0 * cos);
        sessionAvoidAreas.add(new ApiClient.AvoidBox(point.lat - latDelta, point.lon - lonDelta,
                point.lat + latDelta, point.lon + lonDelta));
        while (sessionAvoidAreas.size() > 6) sessionAvoidAreas.remove(0);
    }

    private void reroute(double lat, double lon, boolean manual) {
        if (rerouting) {
            if (manual) sendStatus("A reroute is already in progress.");
            return;
        }
        rerouting = true;
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(
                NOTIFICATION_ID, notification("Rerouting", "Finding a new route"));
        executor.execute(() -> {
            try {
                String json = hasWaypoint
                        ? ApiClient.routeViaSync(this, lat, lon, waypointLat, waypointLon, destLat, destLon, mode, sessionAvoidAreas)
                        : ApiClient.routeSync(this, lat, lon, destLat, destLon, mode, sessionAvoidAreas);
                JSONObject state = new JSONObject();
                state.put("routeIndex", 0);
                state.put("destLat", destLat);
                state.put("destLon", destLon);
                state.put("mode", mode);
                state.put("response", new JSONObject(json));
                if (hasWaypoint) {
                    state.put("hasWaypoint", true);
                    state.put("waypointLat", waypointLat);
                    state.put("waypointLon", waypointLon);
                    state.put("waypointName", waypointName);
                }
                ActiveRouteStore.save(this, state);
                routeIndex = 0;
                route = RouteMath.parse(json, 0);
                lastSegmentIndex = -1;
                lastProgressOffset = 0;
                activeInstructionKey = "";
                announcedEarly = false;
                announcedNear = false;
                offRouteHits = 0;
                Intent changed = new Intent(ACTION_ROUTE_UPDATED).setPackage(getPackageName());
                sendBroadcast(changed);
                if (manual) sendStatus(sessionAvoidAreas.isEmpty() ? "Route refreshed." : "New route avoids the selected road ahead.");
            } catch (Exception e) {
                Log.w("ClearRouteNavigation", "Reroute failed", e);
                sendStatus("Could not find a new route. Continue safely and try again when possible.");
            } finally {
                rerouting = false;
            }
        });
    }

    private void sendStatus(String message) {
        Intent status = new Intent(ACTION_STATUS).setPackage(getPackageName());
        status.putExtra("message", message == null ? "" : message);
        sendBroadcast(status);
    }

    private void loadRoute() throws Exception {
        JSONObject state = ActiveRouteStore.load(this);
        if (state == null) {
            route = null;
            return;
        }
        routeIndex = state.optInt("routeIndex", routeIndex);
        destLat = state.optDouble("destLat", destLat);
        destLon = state.optDouble("destLon", destLon);
        mode = normaliseMode(state.optString("mode", mode));
        hasWaypoint = state.optBoolean("hasWaypoint", false);
        waypointLat = state.optDouble("waypointLat", 0);
        waypointLon = state.optDouble("waypointLon", 0);
        waypointName = state.optString("waypointName", "Stop");
        route = RouteMath.parse(state.getJSONObject("response").toString(), routeIndex);
    }

    private Notification notification(String title, String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent content = PendingIntent.getActivity(this, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, NavigationService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 2, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Action stopAction = new Notification.Action.Builder(null, "Stop", stopPi).build();
        Notification.Builder builder = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_nav_notification)
                .setContentTitle(title)
                .setContentText(text)
                .setContentIntent(content)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .addAction(stopAction);
        if (Build.VERSION.SDK_INT >= 28) builder.setCategory(Notification.CATEGORY_NAVIGATION);
        else builder.setCategory(Notification.CATEGORY_SERVICE);
        return builder.build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, getString(R.string.nav_channel_name), NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Turn-by-turn navigation instructions");
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }

    private void stopLocationUpdates() {
        try { if (locationManager != null) locationManager.removeUpdates(this); } catch (Exception ignored) {}
        try {
            if (fusedLocationClient != null && fusedLocationCallback != null) {
                fusedLocationClient.removeLocationUpdates(fusedLocationCallback);
            }
        } catch (Exception ignored) {}
    }

    private void stopNavigation(String reason) {
        stopLocationUpdates();
        ActiveRouteStore.clear(this);
        Intent stopped = new Intent(ACTION_STOPPED).setPackage(getPackageName());
        stopped.putExtra("reason", reason == null ? "stopped" : reason);
        sendBroadcast(stopped);
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private static String formatDistance(double metres) {
        if (metres < 950) return Math.max(10, Math.round(metres / 10.0) * 10) + " m";
        return String.format(Locale.UK, "%.1f km", metres / 1000.0);
    }

    private static String spokenDistance(double metres) {
        if (metres < 950) return Math.max(10, Math.round(metres / 10.0) * 10) + " metres";
        return String.format(Locale.UK, "%.1f kilometres", metres / 1000.0);
    }

    private static String formatTime(long seconds) {
        long minutes = Math.max(1, Math.round(seconds / 60.0));
        if (minutes < 60) return minutes + " min";
        long hrs = minutes / 60;
        long mins = minutes % 60;
        return mins == 0 ? hrs + " hr" : hrs + " hr " + mins + " min";
    }

    @Override public void onInit(int status) {
        if (status != TextToSpeech.SUCCESS || tts == null) {
            if (!triedTtsFallback && configuredTtsEngine != null && !configuredTtsEngine.trim().isEmpty()) {
                triedTtsFallback = true;
                Log.w("ClearRouteTTS", "Selected TTS engine failed; falling back to Android default");
                try { if (tts != null) tts.shutdown(); } catch (Exception ignored) {}
                configuredTtsEngine = "";
                try { tts = new TextToSpeech(this, this); } catch (Exception ignored) {}
            }
            return;
        }

        String voiceName = getSharedPreferences("clearroute_local", MODE_PRIVATE).getString("tts_voice", "");
        boolean exactVoiceSet = false;
        if (voiceName != null && !voiceName.trim().isEmpty()) {
            try {
                if (tts.getVoices() != null) {
                    for (Voice voice : tts.getVoices()) {
                        if (voice != null && voiceName.equals(voice.getName())) {
                            exactVoiceSet = tts.setVoice(voice) == TextToSpeech.SUCCESS;
                            break;
                        }
                    }
                }
            } catch (Exception e) {
                Log.w("ClearRouteTTS", "Could not apply selected TTS voice", e);
            }
        }
        if (!exactVoiceSet) tts.setLanguage(Locale.UK);
        try {
            tts.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build());
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String utteranceId) {
                    Log.d("ClearRouteTTS", "Speech started: " + utteranceId);
                }
                @Override public void onDone(String utteranceId) {
                    Log.d("ClearRouteTTS", "Speech completed: " + utteranceId);
                }
                @Override public void onError(String utteranceId) {
                    Log.w("ClearRouteTTS", "Speech synthesis failed: " + utteranceId);
                }
                @Override public void onError(String utteranceId, int errorCode) {
                    Log.w("ClearRouteTTS", "Speech synthesis failed: " + utteranceId + " code=" + errorCode);
                }
            });
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not configure navigation audio attributes", e);
        }
        ttsReady = true;
        try {
            Voice active = tts.getVoice();
            Log.i("ClearRouteTTS", "Navigation TTS ready: engine="
                    + (configuredTtsEngine == null || configuredTtsEngine.isEmpty() ? "system-default" : configuredTtsEngine)
                    + " voice=" + (active == null ? "default" : active.getName()));
        } catch (Exception ignored) {}
    }

    @Override public void onDestroy() {
        ttsReady = false;
        stopLocationUpdates();
        if (tts != null) {
            try { tts.stop(); tts.shutdown(); } catch (Exception ignored) {}
        }
        executor.shutdownNow();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
    @Override public void onProviderEnabled(String provider) {}
    @Override public void onProviderDisabled(String provider) {}
}
