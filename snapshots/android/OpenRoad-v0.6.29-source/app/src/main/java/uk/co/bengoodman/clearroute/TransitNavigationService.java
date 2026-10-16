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
import android.os.Build;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.Nullable;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Foreground owner for public-transport navigation.
 *
 * The WebView remains responsible for the rich coloured UI, but this service owns the
 * active transit journey and location updates while the activity is paused/locked. This
 * prevents a screen lock or Android activity recreation from cancelling the journey.
 */
public final class TransitNavigationService extends Service implements LocationListener {
    public static final String ACTION_UPDATE = "uk.co.bengoodman.clearroute.TRANSIT_UPDATE";
    public static final String ACTION_STOPPED = "uk.co.bengoodman.clearroute.TRANSIT_STOPPED";
    public static final String ACTION_STOP = "uk.co.bengoodman.clearroute.TRANSIT_STOP";
    private static final String CHANNEL_ID = "openroad_transit_navigation";
    private static final int NOTIFICATION_ID = 4208;

    private LocationManager locationManager;
    private FusedLocationProviderClient fused;
    private LocationCallback fusedCallback;
    private JSONObject state;
    private JSONArray legs;
    private int legIndex = 0;
    private boolean platformStarted = false;

    @Override public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        fused = LocationServices.getFusedLocationProviderClient(this);
        fusedCallback = new LocationCallback() {
            @Override public void onLocationResult(LocationResult result) {
                if (result != null && result.getLastLocation() != null) handleLocation(result.getLastLocation());
            }
        };
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopTransit("stopped");
            return START_NOT_STICKY;
        }
        startForeground(NOTIFICATION_ID, notification("Public transport navigation", "Restoring journey…"));
        if (!loadState()) {
            stopTransit("error");
            return START_NOT_STICKY;
        }
        requestLocationUpdates();
        return START_STICKY;
    }

    private boolean loadState() {
        try {
            state = ActiveRouteStore.load(this);
            if (state == null || !"transit".equals(state.optString("mode"))) return false;
            int routeIndex = state.optInt("routeIndex", 0);
            JSONObject response = state.optJSONObject("response");
            JSONArray routes = response == null ? null : response.optJSONArray("routes");
            JSONObject route = routes == null ? null : routes.optJSONObject(Math.max(0, Math.min(routeIndex, routes.length() - 1)));
            legs = route == null ? null : route.optJSONArray("transitLegs");
            if (legs == null || legs.length() == 0) return false;
            legIndex = Math.max(0, Math.min(state.optInt("transitLegIndex", 0), legs.length() - 1));
            updateNotification(null);
            return true;
        } catch (Exception e) {
            Log.w("OpenRoadTransitNav", "Could not restore transit navigation", e);
            return false;
        }
    }

    private void requestLocationUpdates() {
        stopLocationUpdates();
        if (!hasLocationPermission()) return;
        try {
            LocationRequest request = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1500L)
                    .setMinUpdateIntervalMillis(900L)
                    .setWaitForAccurateLocation(false)
                    .build();
            fused.requestLocationUpdates(request, fusedCallback, Looper.getMainLooper())
                    .addOnFailureListener(e -> startPlatformUpdates());
            return;
        } catch (Exception e) {
            Log.w("OpenRoadTransitNav", "Fused location unavailable", e);
        }
        startPlatformUpdates();
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void startPlatformUpdates() {
        if (platformStarted || locationManager == null || !hasLocationPermission()) return;
        platformStarted = true;
        try {
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER))
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1200L, 1f, this, Looper.getMainLooper());
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER))
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1800L, 1f, this, Looper.getMainLooper());
        } catch (Exception e) {
            Log.w("OpenRoadTransitNav", "Platform location unavailable", e);
        }
    }

    private void handleLocation(Location location) {
        if (location == null || legs == null || legs.length() == 0) return;
        try {
            JSONObject leg = legs.optJSONObject(legIndex);
            double toLat = leg == null ? Double.NaN : leg.optDouble("toLat", Double.NaN);
            double toLon = leg == null ? Double.NaN : leg.optDouble("toLon", Double.NaN);
            float[] result = new float[1];
            double distance = Double.NaN;
            if (Double.isFinite(toLat) && Double.isFinite(toLon)) {
                Location.distanceBetween(location.getLatitude(), location.getLongitude(), toLat, toLon, result);
                distance = result[0];
            }
            double threshold = "walk".equals(normaliseMode(leg == null ? "" : leg.optString("mode"))) ? 35.0 : 70.0;
            if (Double.isFinite(distance) && distance <= threshold && legIndex < legs.length() - 1) {
                legIndex++;
                state.put("transitLegIndex", legIndex);
                ActiveRouteStore.save(this, state);
                leg = legs.optJSONObject(legIndex);
                toLat = leg == null ? Double.NaN : leg.optDouble("toLat", Double.NaN);
                toLon = leg == null ? Double.NaN : leg.optDouble("toLon", Double.NaN);
                if (Double.isFinite(toLat) && Double.isFinite(toLon)) {
                    Location.distanceBetween(location.getLatitude(), location.getLongitude(), toLat, toLon, result);
                    distance = result[0];
                }
            }
            Intent update = new Intent(ACTION_UPDATE).setPackage(getPackageName());
            update.putExtra("lat", location.getLatitude());
            update.putExtra("lon", location.getLongitude());
            update.putExtra("bearing", location.hasBearing() ? location.getBearing() : 0f);
            update.putExtra("hasBearing", location.hasBearing());
            update.putExtra("speed", location.hasSpeed() ? location.getSpeed() : 0f);
            update.putExtra("legIndex", legIndex);
            update.putExtra("distanceToLegEnd", Double.isFinite(distance) ? distance : -1d);
            sendBroadcast(update);
            updateNotification(location);
        } catch (Exception e) {
            Log.w("OpenRoadTransitNav", "Could not update transit navigation", e);
        }
    }

    private void updateNotification(@Nullable Location location) {
        JSONObject leg = legs == null ? null : legs.optJSONObject(legIndex);
        String mode = normaliseMode(leg == null ? "" : leg.optString("mode"));
        String service = leg == null ? "" : leg.optString("service", leg.optString("line", ""));
        String to = leg == null ? "" : leg.optString("toName", leg.optString("destination", ""));
        String title;
        if ("walk".equals(mode)) title = "Walk";
        else if (!service.isEmpty()) title = "Take " + service;
        else title = "Continue by public transport";
        String text = to.isEmpty() ? "Public transport navigation active" : "Towards " + to;
        ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(NOTIFICATION_ID, notification(title, text));
    }

    private Notification notification(String title, String text) {
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, TransitNavigationService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Action stopAction = new Notification.Action.Builder(null, "Stop", stopPi).build();
        Notification.Builder b = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_nav_notification)
                .setContentTitle(title)
                .setContentText(text)
                .setContentIntent(content)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .addAction(stopAction);
        if (Build.VERSION.SDK_INT >= 28) b.setCategory(Notification.CATEGORY_NAVIGATION);
        return b.build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel c = new NotificationChannel(CHANNEL_ID, "Public transport navigation", NotificationManager.IMPORTANCE_LOW);
            c.setDescription("Keeps an active public transport journey running while the phone is locked");
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);
        }
    }

    private static String normaliseMode(String value) {
        if (value == null) return "transit";
        value = value.toLowerCase();
        if (value.contains("walk")) return "walk";
        if (value.contains("bus") || value.contains("coach")) return "bus";
        if (value.contains("rail") || value.contains("train")) return "rail";
        if (value.contains("tram")) return "tram";
        if (value.contains("tube") || value.contains("underground") || value.contains("metro")) return "tube";
        if (value.contains("ferry")) return "ferry";
        return value;
    }

    private void stopLocationUpdates() {
        try { if (fused != null && fusedCallback != null) fused.removeLocationUpdates(fusedCallback); } catch (Exception ignored) {}
        try { if (locationManager != null) locationManager.removeUpdates(this); } catch (Exception ignored) {}
    }

    private void stopTransit(String reason) {
        stopLocationUpdates();
        getSharedPreferences("clearroute_local", MODE_PRIVATE).edit().putBoolean(TransitPreloadReceiver.PREF_TRANSIT_NAV_ACTIVE, false).apply();
        ActiveRouteStore.clear(this);
        sendBroadcast(new Intent(ACTION_STOPPED).setPackage(getPackageName()).putExtra("reason", reason));
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override public void onLocationChanged(Location location) { handleLocation(location); }
    @Override public void onProviderEnabled(String provider) { }
    @Override public void onProviderDisabled(String provider) { }
    @Override public void onDestroy() { stopLocationUpdates(); super.onDestroy(); }
    @Nullable @Override public IBinder onBind(Intent intent) { return null; }
}
