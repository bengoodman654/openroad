package uk.co.bengoodman.clearroute;

import android.Manifest;
import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.provider.ContactsContract;
import android.database.Cursor;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.util.Log;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.view.WindowManager;

import androidx.webkit.WebViewAssetLoader;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;
import com.google.android.gms.tasks.CancellationTokenSource;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class MainActivity extends Activity implements LocationListener {
    private static final int REQ_LOCATION = 1201;
    private static final int REQ_NOTIFICATIONS = 1202;
    private static final int REQ_CONTACTS = 1203;
    private static final int REQ_BACKGROUND_LOCATION = 1204;
    private static final String LOCAL_PREFS = "clearroute_local";
    private static final String PREF_ENHANCED_LOCATION = "enhanced_location";
    private static final String PREF_HOME = "home";
    private static final String PREF_NAV_ALERT_MODE = "navigation_alert_mode";
    private static final String PREF_TTS_ENGINE = "tts_engine";
    private static final String PREF_TTS_VOICE = "tts_voice";
    private static final String PREF_SEARCH_BIAS = "search_bias";
    private static final String PREF_TRAFFIC_VISIBLE = "traffic_visible";
    private static final String PREF_TRAVEL_MODE = "travel_mode";
    private static final String PREF_BUNDLED_TOMTOM_REVISION = "bundled_tomtom_revision";
    private static final String PREF_BUNDLED_TRANSIT_REVISION = "bundled_transit_revision";
    private static final String PREF_AVOID_MOTORWAYS = "avoid_motorways";
    private static final String PREF_AVOID_TOLLS = "avoid_tolls";
    private static final String PREF_AVOID_FERRIES = "avoid_ferries";
    private static final String PREF_PREFER_MOTORWAYS = "prefer_motorways";
    private static final String PREF_TRANSPORTAPI_ID = "transportapi_id";
    // Legacy plaintext preference, migrated into Android Keystore on startup.
    private static final String PREF_TRANSPORTAPI_KEY = "transportapi_key";
    private static final String SECRET_TRANSPORTAPI_KEY = "transportapi_key";
    private static final String SECRET_BODS_KEY = "bods_api_key";
    private static final String SECRET_TFL_KEY = "tfl_api_key";
    private static final String SECRET_TFL_SECONDARY_KEY = "tfl_secondary_api_key";
    private static final String SECRET_DARWIN_USER = "darwin_username";
    private static final String SECRET_DARWIN_PASSWORD = "darwin_password";
    private static final long LOCATION_TIMEOUT_MS = 15000L;

    private WebView webView;
    private OpenRoadUpdater updater;
    private LocationManager locationManager;
    private FusedLocationProviderClient fusedLocationClient;
    private LocationCallback fusedLocationCallback;
    private CancellationTokenSource currentLocationToken;
    private final Handler locationHandler = new Handler(Looper.getMainLooper());
    private Location lastLocation;
    private long lastLocationElapsed = 0L;
    private String lastRouteResponse = "";
    private volatile long latestRouteRequestId = 0L;
    private volatile long latestAlongRouteRequestId = 0L;
    private volatile double latestNavigationLat = Double.NaN, latestNavigationLon = Double.NaN;
    private boolean receiversRegistered = false;
    private boolean webReady = false;
    private WebViewAssetLoader assetLoader;
    private TextToSpeech voicePreviewTts;

    private final BroadcastReceiver navReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            if (TransitNavigationService.ACTION_STOPPED.equals(intent.getAction())) {
                String reason = intent.getStringExtra("reason");
                runOnUiThread(() -> {
                    startLocationUpdates();
                    js("window.ClearRoute && ClearRoute.onNavigationStopped(" + JSONObject.quote(reason == null ? "stopped" : reason) + ")");
                });
                return;
            }
            if (TransitNavigationService.ACTION_UPDATE.equals(intent.getAction())) {
                JSONObject o = new JSONObject();
                try {
                    o.put("lat", intent.getDoubleExtra("lat", 0));
                    o.put("lon", intent.getDoubleExtra("lon", 0));
                    o.put("bearing", intent.getFloatExtra("bearing", 0));
                    o.put("hasBearing", intent.getBooleanExtra("hasBearing", false));
                    o.put("speed", intent.getFloatExtra("speed", 0));
                    o.put("legIndex", intent.getIntExtra("legIndex", 0));
                    o.put("distanceToLegEnd", intent.getDoubleExtra("distanceToLegEnd", -1));
                    js("window.ClearRoute && ClearRoute.onTransitNavigationUpdate(" + o + ")");
                } catch (Exception ignored) {}
                return;
            }
            if (NavigationService.ACTION_ROUTE_UPDATED.equals(intent.getAction())) {
                loadActiveRouteIntoWebView(false);
                return;
            }
            if (NavigationService.ACTION_STATUS.equals(intent.getAction())) {
                String message = intent.getStringExtra("message");
                js("window.ClearRoute && ClearRoute.onNavigationStatus(" + JSONObject.quote(message == null ? "" : message) + ")");
                return;
            }
            if (NavigationService.ACTION_STOPPED.equals(intent.getAction())) {
                String reason = intent.getStringExtra("reason");
                runOnUiThread(() -> {
                    startLocationUpdates();
                    js("window.ClearRoute && ClearRoute.onNavigationStopped(" + JSONObject.quote(reason == null ? "stopped" : reason) + ")");
                });
                return;
            }
            if (!NavigationService.ACTION_UPDATE.equals(intent.getAction())) return;
            JSONObject o = new JSONObject();
            try {
                double navLat = intent.getDoubleExtra("lat", 0);
                double navLon = intent.getDoubleExtra("lon", 0);
                latestNavigationLat = navLat;
                latestNavigationLon = navLon;
                o.put("lat", navLat);
                o.put("lon", navLon);
                o.put("bearing", intent.getFloatExtra("bearing", 0));
                o.put("hasBearing", intent.getBooleanExtra("hasBearing", false));
                o.put("speed", intent.getFloatExtra("speed", 0));
                o.put("speedLimitKmh", intent.getIntExtra("speedLimitKmh", -1));
                o.put("instruction", intent.getStringExtra("instruction"));
                o.put("maneuver", intent.getStringExtra("maneuver"));
                o.put("instructionDistance", intent.getDoubleExtra("instructionDistance", 0));
                o.put("remainingDistance", intent.getDoubleExtra("remainingDistance", 0));
                o.put("remainingSeconds", intent.getLongExtra("remainingSeconds", 0));
                o.put("visualAlert", intent.getBooleanExtra("visualAlert", false));
                o.put("alertPhase", intent.getStringExtra("alertPhase"));
                js("window.ClearRoute && ClearRoute.onNavigationUpdate(" + o + ")");
            } catch (Exception ignored) {}
        }
    };

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        boolean systemDark = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        if (systemDark) {
            getWindow().setStatusBarColor(Color.rgb(32,33,36));
            getWindow().setNavigationBarColor(Color.rgb(32,33,36));
            if (Build.VERSION.SDK_INT >= 23) getWindow().getDecorView().setSystemUiVisibility(0);
        }
        // Public-transport navigation is persisted in ActiveRouteStore and owned by a foreground
        // service while the screen is locked. Only clear a stale preload-suppression flag when no
        // transit route is actually active.
        JSONObject startupRoute = ActiveRouteStore.load(this);
        boolean transitStillActive = startupRoute != null && "transit".equals(startupRoute.optString("mode"));
        if (!transitStillActive) getSharedPreferences("clearroute_local", MODE_PRIVATE).edit().putBoolean(TransitPreloadReceiver.PREF_TRANSIT_NAV_ACTIVE, false).apply();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        locationManager = (LocationManager) getSystemService(LOCATION_SERVICE);
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
        fusedLocationCallback = new LocationCallback() {
            @Override public void onLocationResult(LocationResult result) {
                if (result == null) return;
                Location location = result.getLastLocation();
                if (location != null) acceptLocation(location, "fused");
            }
        };

        // Personal build: v0.6.8 deliberately re-seeds the owner's bundled TomTom key once.
        // This repairs installs that retained an older/stale encrypted value during the provider
        // settings migration, while still allowing a manually changed key to persist afterwards.
        if (hasBundled(BuildConfig.BUNDLED_TOMTOM_API_KEY)) {
            int bundledRevision = localPrefs().getInt(PREF_BUNDLED_TOMTOM_REVISION, 0);
            if (SecureStore.getApiKey(this).isEmpty() || bundledRevision < 610) {
                try {
                    SecureStore.saveApiKey(this, BuildConfig.BUNDLED_TOMTOM_API_KEY);
                    localPrefs().edit().putInt(PREF_BUNDLED_TOMTOM_REVISION, 610).apply();
                } catch (Exception e) { Log.w("OpenRoad", "Could not seed bundled TomTom key", e); }
            }
        }

        // Personal build: optional public-transport credentials can also be bundled and are
        // copied into Android Keystore on first launch. Empty build fields are ignored.
        seedBundledTransitCredentials();

        // Migrate the pre-0.6.6 TransportAPI key out of ordinary SharedPreferences.
        String legacyTransportKey = localPrefs().getString(PREF_TRANSPORTAPI_KEY, "");
        if (!legacyTransportKey.isEmpty()) {
            try {
                if (SecureStore.getSecret(this, SECRET_TRANSPORTAPI_KEY).isEmpty())
                    SecureStore.saveSecret(this, SECRET_TRANSPORTAPI_KEY, legacyTransportKey);
                localPrefs().edit().remove(PREF_TRANSPORTAPI_KEY).apply();
            } catch (Exception e) { Log.w("OpenRoadTransit", "Could not migrate TransportAPI credential", e); }
        }

        // Keep startup deliberately simple: the local app shell must never be hidden behind
        // a map/network watchdog. If the basemap is slow or unavailable, OpenRoad's controls
        // remain usable and the map layer can recover independently.
        webView = new WebView(this);
        setContentView(webView);
        configureWebView();
        updater = new OpenRoadUpdater(this);
        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html");
        requestLocationPermission();
        if (localPrefs().getBoolean(TransitPreloadReceiver.PREF_ENABLED, true)) TransitPreloadReceiver.schedule(this);
    }

    private void seedBundledTransitCredentials() {
        try {
            // v0.6.10: re-seed the owner's supplied credentials exactly once. Previous builds
            // could preserve stale/manually mistyped values because bundled credentials were
            // only copied when a store entry was empty. After this one-time repair, later
            // manual changes are preserved normally.
            int revision = localPrefs().getInt(PREF_BUNDLED_TRANSIT_REVISION, 0);
            boolean repair = revision < 610;

            if (hasBundled(BuildConfig.BUNDLED_BODS_API_KEY) && (repair || SecureStore.getSecret(this, SECRET_BODS_KEY).isEmpty()))
                SecureStore.saveSecret(this, SECRET_BODS_KEY, BuildConfig.BUNDLED_BODS_API_KEY);
            if (hasBundled(BuildConfig.BUNDLED_TFL_API_KEY) && (repair || SecureStore.getSecret(this, SECRET_TFL_KEY).isEmpty()))
                SecureStore.saveSecret(this, SECRET_TFL_KEY, BuildConfig.BUNDLED_TFL_API_KEY);
            if (hasBundled(BuildConfig.BUNDLED_TFL_SECONDARY_API_KEY) && (repair || SecureStore.getSecret(this, SECRET_TFL_SECONDARY_KEY).isEmpty()))
                SecureStore.saveSecret(this, SECRET_TFL_SECONDARY_KEY, BuildConfig.BUNDLED_TFL_SECONDARY_API_KEY);
            if (hasBundled(BuildConfig.BUNDLED_DARWIN_USERNAME) && (repair || SecureStore.getSecret(this, SECRET_DARWIN_USER).isEmpty()))
                SecureStore.saveSecret(this, SECRET_DARWIN_USER, BuildConfig.BUNDLED_DARWIN_USERNAME);
            if (hasBundled(BuildConfig.BUNDLED_DARWIN_PASSWORD) && (repair || SecureStore.getSecret(this, SECRET_DARWIN_PASSWORD).isEmpty()))
                SecureStore.saveSecret(this, SECRET_DARWIN_PASSWORD, BuildConfig.BUNDLED_DARWIN_PASSWORD);
            if (hasBundled(BuildConfig.BUNDLED_TRANSPORTAPI_APP_ID) && (repair || localPrefs().getString(PREF_TRANSPORTAPI_ID, "").isEmpty()))
                localPrefs().edit().putString(PREF_TRANSPORTAPI_ID, BuildConfig.BUNDLED_TRANSPORTAPI_APP_ID).apply();
            if (hasBundled(BuildConfig.BUNDLED_TRANSPORTAPI_APP_KEY) && (repair || SecureStore.getSecret(this, SECRET_TRANSPORTAPI_KEY).isEmpty()))
                SecureStore.saveSecret(this, SECRET_TRANSPORTAPI_KEY, BuildConfig.BUNDLED_TRANSPORTAPI_APP_KEY);

            if (repair) localPrefs().edit().putInt(PREF_BUNDLED_TRANSIT_REVISION, 610).apply();
        } catch (Exception e) {
            Log.w("OpenRoadTransit", "Could not seed bundled public-transport credentials", e);
        }
    }

    private static boolean hasBundled(String value) {
        return value != null && !value.trim().isEmpty();
    }

    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setGeolocationEnabled(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        assetLoader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        webView.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return assetLoader.shouldInterceptRequest(request.getUrl());
            }

            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                Log.d("ClearRouteWeb", "Local app page finished loading: " + url);
            }

            @Override public void onReceivedError(WebView view, WebResourceRequest request, android.webkit.WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame()) {
                    Log.e("ClearRouteWeb", "Main page load error: " + (error == null ? "unknown" : error.getDescription()));
                }
            }

            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return false;
                Uri uri = request.getUrl();
                if (uri != null && "appassets.androidplatform.net".equalsIgnoreCase(uri.getHost())) return false;
                if (uri != null && ("https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme()))) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (Exception ignored) {}
                }
                // Never let an external attribution/help link replace the trusted local app page
                // while the native Javascript bridge is attached.
                return true;
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onConsoleMessage(ConsoleMessage message) {
                Log.d("ClearRouteWeb", message.message() + " @ " + message.sourceId() + ":" + message.lineNumber());
                return true;
            }
        });
        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true);
        webView.addJavascriptInterface(new Bridge(), "ClearRouteBridge");
    }

    @Override protected void onResume() {
        super.onResume();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        registerNavReceivers();
        if (ActiveRouteStore.exists(this)) {
            stopLocationUpdates();
            if (webReady) loadActiveRouteIntoWebView(true);
        } else {
            startLocationUpdates();
            if (webReady) js("window.ClearRoute && ClearRoute.onNavigationStopped('sync')");
        }
    }

    @Override protected void onPause() {
        super.onPause();
        stopLocationUpdates();
        unregisterNavReceivers();
    }

    @Override protected void onDestroy() {
        locationHandler.removeCallbacksAndMessages(null);
        if (currentLocationToken != null) currentLocationToken.cancel();
        if (voicePreviewTts != null) {
            try { voicePreviewTts.stop(); voicePreviewTts.shutdown(); } catch (Exception ignored) {}
            voicePreviewTts = null;
        }
        if (updater != null) updater.shutdown();
        if (webView != null) webView.destroy();
        super.onDestroy();
    }

    private SharedPreferences localPrefs() {
        return getSharedPreferences(LOCAL_PREFS, MODE_PRIVATE);
    }

    private boolean enhancedLocationEnabled() {
        return localPrefs().getBoolean(PREF_ENHANCED_LOCATION, true);
    }

    private void requestLocationPermission() {
        if (Build.VERSION.SDK_INT >= 23 && !hasLocationPermission()) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, REQ_LOCATION);
        } else {
            startLocationUpdates();
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATIONS);
        }
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean isLocationEnabled() {
        if (locationManager == null) return false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) return locationManager.isLocationEnabled();
        try {
            return locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                    locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        } catch (Exception ignored) {
            return false;
        }
    }

    private Location bestLastKnownLocation() {
        if (!hasLocationPermission() || locationManager == null) return null;
        Location best = null;
        String[] providers = {LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER, LocationManager.PASSIVE_PROVIDER};
        for (String provider : providers) {
            try {
                Location candidate = locationManager.getLastKnownLocation(provider);
                if (candidate == null) continue;
                if (best == null || candidate.getTime() > best.getTime() ||
                        (candidate.getTime() == best.getTime() && candidate.hasAccuracy() &&
                                (!best.hasAccuracy() || candidate.getAccuracy() < best.getAccuracy()))) {
                    best = candidate;
                }
            } catch (Exception e) {
                Log.w("ClearRouteLocation", "Could not read last location from " + provider, e);
            }
        }
        return best;
    }

    private void startLocationUpdates() {
        if (ActiveRouteStore.exists(this)) return; // NavigationService owns high-frequency fixes while navigating.
        if (!hasLocationPermission() || locationManager == null) return;
        if (!isLocationEnabled()) {
            if (webReady) js("window.ClearRoute && ClearRoute.onLocationStatus('disabled')");
            return;
        }

        Location cached = bestLastKnownLocation();
        if (cached != null && lastLocation == null) acceptLocation(cached, "cached");

        if (enhancedLocationEnabled()) startFusedLocationUpdates();
        else startPlatformLocationUpdates();

        if (webReady && lastLocation == null) {
            js("window.ClearRoute && ClearRoute.onLocationStatus('waiting')");
        }
    }

    private void startPlatformLocationUpdates() {
        if (!hasLocationPermission() || locationManager == null) return;
        try {
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1500L, 1f, this, Looper.getMainLooper());
                Log.d("ClearRouteLocation", "NETWORK_PROVIDER updates requested");
            }
        } catch (Exception e) {
            Log.w("ClearRouteLocation", "NETWORK_PROVIDER request failed", e);
        }
        try {
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 1f, this, Looper.getMainLooper());
                Log.d("ClearRouteLocation", "GPS_PROVIDER updates requested");
            }
        } catch (Exception e) {
            Log.w("ClearRouteLocation", "GPS_PROVIDER request failed", e);
        }
    }

    private void startFusedLocationUpdates() {
        if (!hasLocationPermission() || fusedLocationClient == null) return;
        try {
            LocationRequest request = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 2000L)
                    .setMinUpdateIntervalMillis(1000L)
                    .setWaitForAccurateLocation(false)
                    .build();
            fusedLocationClient.requestLocationUpdates(request, fusedLocationCallback, Looper.getMainLooper())
                    .addOnFailureListener(e -> {
                        Log.w("ClearRouteLocation", "Fused updates failed; using Android providers", e);
                        startPlatformLocationUpdates();
                    });
        } catch (SecurityException e) {
            Log.w("ClearRouteLocation", "Fused updates missing permission", e);
        } catch (Exception e) {
            Log.w("ClearRouteLocation", "Fused updates unavailable", e);
        }
    }

    private void requestFreshLocation() {
        if (!hasLocationPermission()) {
            requestLocationPermission();
            return;
        }
        if (!isLocationEnabled()) {
            js("window.ClearRoute && ClearRoute.onLocationStatus('disabled')");
            try { startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)); } catch (Exception ignored) {}
            return;
        }

        js("window.ClearRoute && ClearRoute.onLocationStatus('waiting')");
        final long requestStarted = SystemClock.elapsedRealtime();
        startLocationUpdates();

        if (enhancedLocationEnabled() && fusedLocationClient != null) {
            try {
                if (currentLocationToken != null) currentLocationToken.cancel();
                currentLocationToken = new CancellationTokenSource();
                fusedLocationClient.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, currentLocationToken.getToken())
                        .addOnSuccessListener(location -> {
                            if (location != null) acceptLocation(location, "fused-current");
                            else Log.w("ClearRouteLocation", "Fused getCurrentLocation returned null");
                        })
                        .addOnFailureListener(e -> Log.w("ClearRouteLocation", "Fused current location failed", e));
            } catch (SecurityException e) {
                Log.w("ClearRouteLocation", "Fused current location missing permission", e);
            } catch (Exception e) {
                Log.w("ClearRouteLocation", "Fused current location unavailable", e);
            }
        }

        locationHandler.postDelayed(() -> {
            if (!webReady) return;
            if (lastLocationElapsed < requestStarted) {
                js("window.ClearRoute && ClearRoute.onLocationStatus('timeout')");
            }
        }, LOCATION_TIMEOUT_MS);
    }

    private void stopLocationUpdates() {
        try { if (locationManager != null) locationManager.removeUpdates(this); } catch (Exception ignored) {}
        try { if (fusedLocationClient != null && fusedLocationCallback != null) fusedLocationClient.removeLocationUpdates(fusedLocationCallback); } catch (Exception ignored) {}
    }

    private void acceptLocation(Location location, String source) {
        if (location == null) return;
        if (Double.isNaN(location.getLatitude()) || Double.isNaN(location.getLongitude())) return;
        lastLocation = location;
        lastLocationElapsed = SystemClock.elapsedRealtime();
        Log.d("ClearRouteLocation", source + " location fix received; accuracy=" + (location.hasAccuracy() ? location.getAccuracy() : -1));
        deliverLocation(location);
    }

    private void deliverLocation(Location location) {
        if (location == null || !webReady) return;
        JSONObject o = new JSONObject();
        try {
            o.put("lat", location.getLatitude());
            o.put("lon", location.getLongitude());
            o.put("accuracy", location.hasAccuracy() ? location.getAccuracy() : 0);
            o.put("bearing", location.hasBearing() ? location.getBearing() : 0);
            o.put("hasBearing", location.hasBearing());
            o.put("speed", location.hasSpeed() ? location.getSpeed() : 0);
            o.put("time", location.getTime());
            js("window.ClearRoute && ClearRoute.onLocation(" + o + ")");
        } catch (Exception ignored) {}
    }

    @Override public void onLocationChanged(Location location) {
        acceptLocation(location, location == null ? "platform" : location.getProvider());
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_LOCATION) {
            if (hasLocationPermission()) requestFreshLocation();
            else if (webReady) js("window.ClearRoute && ClearRoute.onLocationStatus('permission-denied')");
        } else if (requestCode == REQ_CONTACTS) {
            boolean granted = checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED;
            if (webReady) js("window.ClearRoute && ClearRoute.onContactsPermission(" + granted + ")");
        } else if (requestCode == REQ_BACKGROUND_LOCATION) {
            boolean granted = Build.VERSION.SDK_INT < 29 || checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED;
            if (granted) TransitPreloadReceiver.schedule(this);
            if (webReady) js("window.ClearRoute && ClearRoute.onDailyTransitPreloadPermission(" + granted + ")");
        }
    }

    private void registerNavReceivers() {
        if (receiversRegistered) return;
        IntentFilter filter = new IntentFilter();
        filter.addAction(NavigationService.ACTION_UPDATE);
        filter.addAction(NavigationService.ACTION_ROUTE_UPDATED);
        filter.addAction(NavigationService.ACTION_STOPPED);
        filter.addAction(NavigationService.ACTION_STATUS);
        filter.addAction(TransitNavigationService.ACTION_UPDATE);
        filter.addAction(TransitNavigationService.ACTION_STOPPED);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(navReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(navReceiver, filter);
        receiversRegistered = true;
    }

    private void unregisterNavReceivers() {
        if (!receiversRegistered) return;
        try { unregisterReceiver(navReceiver); } catch (Exception ignored) {}
        receiversRegistered = false;
    }

    void deliverUpdateScript(String script) { js(script); }

    private void js(String script) {
        if (webView == null) return;
        webView.post(() -> webView.evaluateJavascript(script, null));
    }

    private void loadActiveRouteIntoWebView(boolean ensureService) {
        try {
            JSONObject state = ActiveRouteStore.load(this);
            if (state == null) {
                js("window.ClearRoute && ClearRoute.onNavigationStopped('sync')");
                return;
            }
            lastRouteResponse = state.getJSONObject("response").toString();
            runOnUiThread(() -> getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
            if ("transit".equals(state.optString("mode"))) {
                if (ensureService) ensureTransitNavigationService();
                js("window.ClearRoute && ClearRoute.onTransitNavigationRestored(" + lastRouteResponse + "," + state.optInt("routeIndex", 0) + "," + state.optInt("transitLegIndex", 0) + ")");
            } else {
                if (ensureService) ensureNavigationService(state);
                js("window.ClearRoute && ClearRoute.onRoute(" + lastRouteResponse + "," + state.optInt("routeIndex", 0) + ",true,0)");
            }
        } catch (Exception e) {
            Log.w("ClearRouteNavigation", "Could not restore active navigation", e);
            ActiveRouteStore.clear(this);
        }
    }

    private void ensureNavigationService(JSONObject state) {
        try {
            Intent service = new Intent(this, NavigationService.class)
                    .putExtra("routeIndex", state.optInt("routeIndex", 0))
                    .putExtra("destLat", state.optDouble("destLat", 0))
                    .putExtra("destLon", state.optDouble("destLon", 0))
                    .putExtra("mode", state.optString("mode", "drive"));
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        } catch (Exception e) {
            Log.w("ClearRouteNavigation", "Could not resume navigation service", e);
        }
    }

    private void ensureTransitNavigationService() {
        try {
            Intent service = new Intent(this, TransitNavigationService.class);
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        } catch (Exception e) {
            Log.w("OpenRoadTransitNav", "Could not resume transit navigation service", e);
        }
    }


    private JSONArray installedTtsEngines() {
        JSONArray out = new JSONArray();
        try {
            PackageManager pm = getPackageManager();
            Intent intent = new Intent(TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE);
            List<ResolveInfo> services = pm.queryIntentServices(intent, PackageManager.MATCH_ALL);
            List<ResolveInfo> sorted = new ArrayList<>(services == null ? Collections.emptyList() : services);
            sorted.sort(Comparator.comparing(info -> {
                CharSequence label = info.loadLabel(pm);
                return label == null ? "" : label.toString().toLowerCase(Locale.UK);
            }));
            java.util.HashSet<String> seenPackages = new java.util.HashSet<>();
            for (ResolveInfo info : sorted) {
                if (info.serviceInfo == null || info.serviceInfo.packageName == null) continue;
                if (!seenPackages.add(info.serviceInfo.packageName)) continue;
                JSONObject item = new JSONObject();
                CharSequence label = info.loadLabel(pm);
                item.put("package", info.serviceInfo.packageName);
                item.put("label", label == null ? info.serviceInfo.packageName : label.toString());
                out.put(item);
            }
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not enumerate TTS engines", e);
        }
        return out;
    }

    private void sendTtsVoices(TextToSpeech probe, String enginePackage) {
        try {
            JSONArray voicesJson = new JSONArray();
            if (probe != null) {
                Set<Voice> voiceSet = probe.getVoices();
                List<Voice> voices = new ArrayList<>(voiceSet == null ? Collections.emptySet() : voiceSet);
                voices.removeIf(v -> v == null || v.getLocale() == null || !"en".equalsIgnoreCase(v.getLocale().getLanguage()));
                voices.sort((a, b) -> {
                    boolean aGb = "GB".equalsIgnoreCase(a.getLocale().getCountry());
                    boolean bGb = "GB".equalsIgnoreCase(b.getLocale().getCountry());
                    if (aGb != bGb) return aGb ? -1 : 1;
                    int q = Integer.compare(b.getQuality(), a.getQuality());
                    if (q != 0) return q;
                    return a.getName().compareToIgnoreCase(b.getName());
                });
                for (Voice voice : voices) {
                    JSONObject item = new JSONObject();
                    item.put("name", voice.getName());
                    item.put("locale", voice.getLocale().toLanguageTag());
                    item.put("quality", voice.getQuality());
                    item.put("network", voice.isNetworkConnectionRequired());
                    voicesJson.put(item);
                }
            }
            JSONObject result = new JSONObject();
            result.put("engine", enginePackage == null ? "" : enginePackage);
            result.put("voices", voicesJson);
            js("window.ClearRoute && ClearRoute.onTtsVoices(" + result + ")");
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not send TTS voices", e);
            js("window.ClearRoute && ClearRoute.onTtsVoiceError('Could not read voices from that speech engine')");
        } finally {
            if (probe != null) {
                try { probe.shutdown(); } catch (Exception ignored) {}
            }
        }
    }

    private void requestTtsVoicesInternal(String requestedEngine) {
        final String engine = requestedEngine == null ? "" : requestedEngine.trim();
        final TextToSpeech[] holder = new TextToSpeech[1];
        TextToSpeech.OnInitListener listener = status -> new Handler(Looper.getMainLooper()).post(() -> {
            TextToSpeech probe = holder[0];
            if (status != TextToSpeech.SUCCESS || probe == null) {
                if (probe != null) try { probe.shutdown(); } catch (Exception ignored) {}
                js("window.ClearRoute && ClearRoute.onTtsVoiceError('That speech engine could not be started')");
                return;
            }
            sendTtsVoices(probe, engine);
        });
        try {
            holder[0] = engine.isEmpty()
                    ? new TextToSpeech(this, listener)
                    : new TextToSpeech(this, listener, engine);
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not initialise TTS engine " + engine, e);
            js("window.ClearRoute && ClearRoute.onTtsVoiceError('That speech engine could not be started')");
        }
    }

    private void previewTtsInternal(String requestedEngine, String requestedVoice) {
        if (voicePreviewTts != null) {
            try { voicePreviewTts.stop(); voicePreviewTts.shutdown(); } catch (Exception ignored) {}
            voicePreviewTts = null;
        }
        final String engine = requestedEngine == null ? "" : requestedEngine.trim();
        final String voiceName = requestedVoice == null ? "" : requestedVoice.trim();
        final TextToSpeech[] holder = new TextToSpeech[1];
        TextToSpeech.OnInitListener listener = status -> new Handler(Looper.getMainLooper()).post(() -> {
            TextToSpeech speaker = holder[0];
            if (status != TextToSpeech.SUCCESS || speaker == null) {
                js("window.ClearRoute && ClearRoute.onTtsVoiceError('Could not preview that voice')");
                return;
            }
            voicePreviewTts = speaker;
            try {
                boolean exactVoice = false;
                if (!voiceName.isEmpty()) {
                    Set<Voice> voices = speaker.getVoices();
                    if (voices != null) {
                        for (Voice voice : voices) {
                            if (voice != null && voiceName.equals(voice.getName())) {
                                exactVoice = speaker.setVoice(voice) == TextToSpeech.SUCCESS;
                                break;
                            }
                        }
                    }
                }
                if (!exactVoice) speaker.setLanguage(Locale.UK);
                speaker.speak("In three hundred metres, turn left onto Queen's Road.", TextToSpeech.QUEUE_FLUSH, null, "clearroute-preview");
            } catch (Exception e) {
                Log.w("ClearRouteTTS", "Voice preview failed", e);
                js("window.ClearRoute && ClearRoute.onTtsVoiceError('Could not preview that voice')");
            }
        });
        try {
            holder[0] = engine.isEmpty()
                    ? new TextToSpeech(this, listener)
                    : new TextToSpeech(this, listener, engine);
        } catch (Exception e) {
            Log.w("ClearRouteTTS", "Could not create preview TTS", e);
            js("window.ClearRoute && ClearRoute.onTtsVoiceError('Could not preview that voice')");
        }
    }

    private static String maskCredential(String value) {
        if (value == null || value.isEmpty()) return "";
        String v = value.trim();
        if (v.length() <= 4) return "****";
        int edge = v.length() <= 8 ? 2 : 4;
        int hidden = Math.max(4, Math.min(12, v.length() - (edge * 2)));
        StringBuilder stars = new StringBuilder();
        for (int i = 0; i < hidden; i++) stars.append('*');
        return v.substring(0, edge) + stars + v.substring(v.length() - edge);
    }

    public final class Bridge {
        @JavascriptInterface public void checkForUpdates() { if(updater != null) updater.check(true); }
        @JavascriptInterface public void installUpdate() { if(updater != null) updater.install(); }

        @JavascriptInterface public boolean hasApiKey() {
            return !SecureStore.getApiKey(MainActivity.this).isEmpty();
        }

        @JavascriptInterface public void saveApiKey(String key) {
            try {
                SecureStore.saveApiKey(MainActivity.this, key);
                js("ClearRoute.onApiKeySaved(true)");
            } catch (Exception e) {
                js("ClearRoute.onApiKeySaved(false)");
            }
        }

        @JavascriptInterface public void clearApiKey() {
            SecureStore.clearApiKey(MainActivity.this);
            js("ClearRoute.onApiKeySaved(false)");
        }

        @JavascriptInterface public String getTrafficApiKey() {
            return SecureStore.getApiKey(MainActivity.this);
        }

        @JavascriptInterface public String getTomTomStatus() {
            try {
                String key = SecureStore.getApiKey(MainActivity.this);
                JSONObject out = new JSONObject();
                out.put("configured", !key.isEmpty());
                out.put("masked", maskCredential(key));
                return out.toString();
            } catch (Exception e) { return "{\"configured\":false,\"masked\":\"\"}"; }
        }

        @JavascriptInterface public String revealTomTomApiKey() {
            return SecureStore.getApiKey(MainActivity.this);
        }

        @JavascriptInterface public void appReady() {
            runOnUiThread(() -> {
                webReady = true;
                if (updater != null) updater.check(false);
                if (ActiveRouteStore.exists(MainActivity.this)) {
                    stopLocationUpdates();
                    loadActiveRouteIntoWebView(true);
                } else if (lastLocation != null) {
                    deliverLocation(lastLocation);
                } else {
                    requestFreshLocation();
                }
            });
        }

        @JavascriptInterface public void requestLocation() {
            runOnUiThread(MainActivity.this::requestFreshLocation);
        }

        @JavascriptInterface public boolean isEnhancedLocationEnabled() {
            return enhancedLocationEnabled();
        }

        @JavascriptInterface public void setEnhancedLocationEnabled(boolean enabled) {
            localPrefs().edit().putBoolean(PREF_ENHANCED_LOCATION, enabled).apply();
            runOnUiThread(() -> {
                stopLocationUpdates();
                startLocationUpdates();
                if (lastLocation == null) requestFreshLocation();
            });
        }

        @JavascriptInterface public String getNavigationAlertMode() {
            String value = localPrefs().getString(PREF_NAV_ALERT_MODE, "voice");
            return ("flash".equals(value) || "silent".equals(value)) ? value : "voice";
        }

        @JavascriptInterface public void setNavigationAlertMode(String value) {
            String mode = ("flash".equals(value) || "silent".equals(value)) ? value : "voice";
            localPrefs().edit().putString(PREF_NAV_ALERT_MODE, mode).apply();
        }

        @JavascriptInterface public boolean isSearchBiasEnabled() {
            return localPrefs().getBoolean(PREF_SEARCH_BIAS, false);
        }

        @JavascriptInterface public void setSearchBiasEnabled(boolean enabled) {
            localPrefs().edit().putBoolean(PREF_SEARCH_BIAS, enabled).apply();
        }

        @JavascriptInterface public boolean isTrafficVisible() {
            return localPrefs().getBoolean(PREF_TRAFFIC_VISIBLE, true);
        }

        @JavascriptInterface public void setTrafficVisible(boolean enabled) {
            localPrefs().edit().putBoolean(PREF_TRAFFIC_VISIBLE, enabled).apply();
        }

        @JavascriptInterface public String getTravelMode() {
            String value = localPrefs().getString(PREF_TRAVEL_MODE, "drive");
            return "cycle".equals(value) || "walk".equals(value) || "transit".equals(value) ? value : "drive";
        }

        @JavascriptInterface public void setTravelMode(String value) {
            String saved = "cycle".equals(value) || "walk".equals(value) || "transit".equals(value) ? value : "drive";
            localPrefs().edit().putString(PREF_TRAVEL_MODE, saved).apply();
        }

        @JavascriptInterface public boolean isAvoidMotorways() { return localPrefs().getBoolean(PREF_AVOID_MOTORWAYS, false); }
        @JavascriptInterface public boolean isAvoidTolls() { return localPrefs().getBoolean(PREF_AVOID_TOLLS, false); }
        @JavascriptInterface public boolean isAvoidFerries() { return localPrefs().getBoolean(PREF_AVOID_FERRIES, false); }
        @JavascriptInterface public boolean isPreferMotorways() { return localPrefs().getBoolean(PREF_PREFER_MOTORWAYS, false); }

        @JavascriptInterface public void setRouteAvoidances(boolean motorways, boolean tolls, boolean ferries, boolean preferMotorways) {
            localPrefs().edit()
                    .putBoolean(PREF_AVOID_MOTORWAYS, motorways)
                    .putBoolean(PREF_AVOID_TOLLS, tolls)
                    .putBoolean(PREF_AVOID_FERRIES, ferries)
                    .putBoolean(PREF_PREFER_MOTORWAYS, preferMotorways)
                    .apply();
        }

        @JavascriptInterface public boolean hasContactsPermission() {
            return checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface public void requestContactsPermission() {
            runOnUiThread(() -> requestPermissions(new String[]{Manifest.permission.READ_CONTACTS}, REQ_CONTACTS));
        }

        /** Return only a bounded, addressed subset for an explicitly enabled map layer. */
        @JavascriptInterface public String getContactMapCandidates() {
            JSONArray out = new JSONArray();
            if (!hasContactsPermission()) return out.toString();
            String[] projection = new String[]{
                ContactsContract.CommonDataKinds.StructuredPostal.DISPLAY_NAME,
                ContactsContract.CommonDataKinds.StructuredPostal.FORMATTED_ADDRESS
            };
            String selection = ContactsContract.CommonDataKinds.StructuredPostal.FORMATTED_ADDRESS + " IS NOT NULL";
            try (Cursor cursor = getContentResolver().query(
                ContactsContract.CommonDataKinds.StructuredPostal.CONTENT_URI,
                projection, selection, null,
                ContactsContract.CommonDataKinds.StructuredPostal.DISPLAY_NAME + " COLLATE NOCASE ASC")) {
                java.util.HashSet<String> unique = new java.util.HashSet<>();
                while (cursor != null && cursor.moveToNext() && out.length() < 15) {
                    String name = cursor.getString(0), addr = cursor.getString(1);
                    if (addr == null || addr.trim().isEmpty()) continue;
                    if (name == null || name.trim().isEmpty()) name = "Contact";
                    if (!unique.add(name.toLowerCase(java.util.Locale.ROOT) + "|" + addr.trim().toLowerCase(java.util.Locale.ROOT))) continue;
                    out.put(new JSONObject().put("name", name).put("address", addr.trim()));
                }
            } catch (Exception e) { Log.w("ClearRouteContacts", "Contacts map query unavailable", e); }
            return out.toString();
        }

        @JavascriptInterface public String getInstalledAppVersion() {
            return BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface public String getContactMatches(String query) {
            JSONArray out = new JSONArray();
            if (!hasContactsPermission() || query == null) return out.toString();
            String q = query.trim();
            // Never expose the address book wholesale to the WebView. Contact rows are returned
            // only in direct response to active user input in the Where to? box.
            if (q.length() < 1) return out.toString();
            String[] projection = new String[]{ContactsContract.CommonDataKinds.StructuredPostal.DISPLAY_NAME,
                    ContactsContract.CommonDataKinds.StructuredPostal.FORMATTED_ADDRESS};
            String selection = ContactsContract.CommonDataKinds.StructuredPostal.DISPLAY_NAME + " LIKE ? AND " + ContactsContract.CommonDataKinds.StructuredPostal.FORMATTED_ADDRESS + " IS NOT NULL";
            String[] args = new String[]{q + "%"};
            try (Cursor c = getContentResolver().query(ContactsContract.CommonDataKinds.StructuredPostal.CONTENT_URI,
                    projection, selection, args, ContactsContract.CommonDataKinds.StructuredPostal.DISPLAY_NAME + " COLLATE NOCASE ASC")) {
                int count = 0, limit = 8;
                if (c != null) while (c.moveToNext() && count < limit) {
                    String name = c.getString(0); String address = c.getString(1);
                    if (address == null || address.trim().isEmpty()) continue;
                    JSONObject item = new JSONObject(); item.put("name", name == null ? "Contact" : name); item.put("address", address.trim()); out.put(item); count++;
                }
            } catch (Exception e) { Log.w("ClearRouteContacts", "Contact search failed", e); }
            return out.toString();
        }

        @JavascriptInterface public void geocodeContactAddress(String name, String address) {
            if (address == null || address.trim().isEmpty()) return;
            ApiClient.search(MainActivity.this, address, null, null, new ApiClient.Callback() {
                @Override public void onSuccess(String json) {
                    try {
                        JSONObject root = new JSONObject(json); JSONArray results = root.optJSONArray("results");
                        JSONObject first = results == null ? null : results.optJSONObject(0);
                        JSONObject pos = first == null ? null : first.optJSONObject("position");
                        if (pos == null) throw new Exception("No geocode");
                        js("ClearRoute.onContactGeocoded(" + JSONObject.quote(name == null ? "Contact" : name) + "," + JSONObject.quote(address) + "," + pos.optDouble("lat") + "," + pos.optDouble("lon") + ")");
                    } catch (Exception e) { js("ClearRoute.onContactGeocodeFailed(" + JSONObject.quote(name == null ? "Contact" : name) + "," + JSONObject.quote(address) + ")"); }
                }
                @Override public void onError(String message) { js("ClearRoute.onContactGeocodeFailed(" + JSONObject.quote(name == null ? "Contact" : name) + "," + JSONObject.quote(address) + ")"); }
            });
        }

        @JavascriptInterface public String getTransportApiCredentials() {
            try {
                String id = localPrefs().getString(PREF_TRANSPORTAPI_ID, "");
                String key = SecureStore.getSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY);
                JSONObject o = new JSONObject();
                o.put("id", id == null ? "" : id);
                o.put("configured", id != null && !id.isEmpty() && !key.isEmpty());
                o.put("maskedKey", maskCredential(key));
                return o.toString();
            } catch (Exception e) { return "{\"id\":\"\",\"configured\":false}"; }
        }

        @JavascriptInterface public void saveTransportApiCredentials(String id, String key) {
            try {
                String cleanId = id == null ? "" : id.trim();
                localPrefs().edit().putString(PREF_TRANSPORTAPI_ID, cleanId).apply();
                if (key != null && !key.trim().isEmpty()) SecureStore.saveSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY, key);
                js("ClearRoute.onTransportApiSaved(true)");
            } catch (Exception e) { js("ClearRoute.onTransportApiSaved(false)"); }
        }

        @JavascriptInterface public String getPublicTransportStatus() {
            try {
                JSONObject o = new JSONObject();
                String transportId = localPrefs().getString(PREF_TRANSPORTAPI_ID, "");
                String transportKey = SecureStore.getSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY);
                String tfl = SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
                String tflSecondary = SecureStore.getSecret(MainActivity.this, SECRET_TFL_SECONDARY_KEY);
                String bods = SecureStore.getSecret(MainActivity.this, SECRET_BODS_KEY);
                String darwinUser = SecureStore.getSecret(MainActivity.this, SECRET_DARWIN_USER);
                o.put("tflConfigured", !tfl.isEmpty()).put("tflMasked", maskCredential(tfl));
                o.put("tflSecondaryConfigured", !tflSecondary.isEmpty()).put("tflSecondaryMasked", maskCredential(tflSecondary));
                o.put("bodsConfigured", !bods.isEmpty()).put("bodsMasked", maskCredential(bods));
                o.put("railDataConfigured", !darwinUser.isEmpty()).put("railDataKeyMasked", maskCredential(darwinUser));
                o.put("transportApiConfigured", !transportId.isEmpty() && !transportKey.isEmpty())
                        .put("transportApiIdMasked", maskCredential(transportId)).put("transportApiMasked", maskCredential(transportKey));
                boolean serverPaired = OpenRoadServerClient.configured(MainActivity.this, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                o.put("openRoadServerConfigured", serverPaired)
                        .put("openRoadServerPaired", serverPaired)
                        .put("openRoadServerUrl", BuildConfig.BUNDLED_OPENROAD_SERVER_URL)
                        .put("openRoadServerDeviceId", serverPaired ? DeviceAuth.deviceId(MainActivity.this) : "");
                o.put("naptan", TransitClient.cacheStatus(MainActivity.this));
                return o.toString();
            } catch (Exception e) { return "{}"; }
        }

        @JavascriptInterface public String revealTransitCredential(String name) {
            if (name == null) return "";
            switch (name) {
                case "bods": return SecureStore.getSecret(MainActivity.this, SECRET_BODS_KEY);
                case "tfl": return SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
                case "tflSecondary": return SecureStore.getSecret(MainActivity.this, SECRET_TFL_SECONDARY_KEY);
                case "transportId": return localPrefs().getString(PREF_TRANSPORTAPI_ID, "");
                case "transportKey": return SecureStore.getSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY);
                case "railData": return SecureStore.getSecret(MainActivity.this, SECRET_DARWIN_USER);
                default: return "";
            }
        }

        @JavascriptInterface public void pairOpenRoadServer(String pairingCode) {
            final String code = pairingCode == null ? "" : pairingCode.trim();
            new Thread(() -> {
                try {
                    OpenRoadServerClient.pair(MainActivity.this, BuildConfig.BUNDLED_OPENROAD_SERVER_URL, code);
                    js("ClearRoute.onOpenRoadServerPairing(true,'Paired securely to this device')");
                } catch (Exception e) {
                    js("ClearRoute.onOpenRoadServerPairing(false," + JSONObject.quote(e.getMessage() == null ? "Pairing failed" : e.getMessage()) + ")");
                }
            }, "OpenRoadServerPair").start();
        }

        @JavascriptInterface public void checkOpenRoadServer() {
            new Thread(() -> {
                try {
                    JSONObject status = OpenRoadServerClient.status(MainActivity.this, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                    js("ClearRoute.onOpenRoadServerCheck(true," + JSONObject.quote(status.toString()) + ")");
                } catch (Exception e) {
                    js("ClearRoute.onOpenRoadServerCheck(false," + JSONObject.quote(e.getMessage() == null ? "Server check failed" : e.getMessage()) + ")");
                }
            }, "OpenRoadServerCheck").start();
        }

        @JavascriptInterface public void removeOpenRoadServerPairing() {
            new Thread(() -> {
                boolean revoked = OpenRoadServerClient.revokeThisDevice(MainActivity.this, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                if (!revoked) DeviceAuth.clearPairing(MainActivity.this);
                js("ClearRoute.onOpenRoadServerRemoved(" + revoked + ")");
            }, "OpenRoadServerRemove").start();
        }

        @JavascriptInterface public void saveBodsApiKey(String key) {
            try {
                if (key != null && !key.trim().isEmpty()) SecureStore.saveSecret(MainActivity.this, SECRET_BODS_KEY, key);
                js("ClearRoute.onTransitCredentialSaved('bods',true)");
            } catch (Exception e) { js("ClearRoute.onTransitCredentialSaved('bods',false)"); }
        }

        @JavascriptInterface public void saveTflApiKey(String key) {
            try {
                if (key != null && !key.trim().isEmpty()) SecureStore.saveSecret(MainActivity.this, SECRET_TFL_KEY, key);
                js("ClearRoute.onTransitCredentialSaved('tfl',true)");
            } catch (Exception e) { js("ClearRoute.onTransitCredentialSaved('tfl',false)"); }
        }

        @JavascriptInterface public void saveTflSecondaryApiKey(String key) {
            try {
                if (key != null && !key.trim().isEmpty()) SecureStore.saveSecret(MainActivity.this, SECRET_TFL_SECONDARY_KEY, key);
                js("ClearRoute.onTransitCredentialSaved('tflSecondary',true)");
            } catch (Exception e) { js("ClearRoute.onTransitCredentialSaved('tflSecondary',false)"); }
        }

        @JavascriptInterface public void saveRailDataApiKey(String key) {
            try {
                if (key != null && !key.trim().isEmpty()) SecureStore.saveSecret(MainActivity.this, SECRET_DARWIN_USER, key);
                js("ClearRoute.onTransitCredentialSaved('railData',true)");
            } catch (Exception e) { js("ClearRoute.onTransitCredentialSaved('railData',false)"); }
        }

        // Live rail board probe: read-only and independent of the bus journey router.
        // Never return, log or embed the consumer key in JavaScript messages.
        @JavascriptInterface public void checkRailDepartures(String stationCode) {
            final String code = stationCode == null ? "" : stationCode.trim().toUpperCase(Locale.UK);
            if (!code.matches("[A-Z]{3}")) {
                js("ClearRoute.onRailDepartures(false,'Enter a three-letter station code.')");
                return;
            }
            new Thread(() -> {
                try {
                    JSONObject result = OpenRoadServerClient.railDepartureBoard(MainActivity.this,code,BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                    js("ClearRoute.onRailDepartures(true," + result + ")");
                } catch (Exception e) {
                    // Relay only a bounded app-owned error string. No upstream keys or bodies.
                    String message=e.getMessage()==null?"Rail departures are unavailable.":e.getMessage();
                    if(message.length()>180)message="Rail departures are unavailable. Check the private server configuration.";
                    js("ClearRoute.onRailDepartures(false," + JSONObject.quote(message) + ")");
                }
            }, "OpenRoadRailBoard").start();
        }

        @JavascriptInterface public void openExternalUrl(String url) {
            runOnUiThread(() -> {
                try {
                    Uri uri = Uri.parse(url == null ? "" : url);
                    if ("https".equalsIgnoreCase(uri.getScheme())) startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {}
            });
        }

        @JavascriptInterface public void openVoiceSettings() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent("com.android.settings.TTS_SETTINGS"));
                } catch (Exception e) {
                    try { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
                    catch (Exception ignored) { js("ClearRoute.onError('Could not open Android voice settings')"); }
                }
            });
        }


        @JavascriptInterface public String getTtsEngines() {
            return installedTtsEngines().toString();
        }

        @JavascriptInterface public String getTtsChoice() {
            try {
                JSONObject choice = new JSONObject();
                choice.put("engine", localPrefs().getString(PREF_TTS_ENGINE, ""));
                choice.put("voice", localPrefs().getString(PREF_TTS_VOICE, ""));
                return choice.toString();
            } catch (Exception e) {
                return "{\"engine\":\"\",\"voice\":\"\"}";
            }
        }

        @JavascriptInterface public void requestTtsVoices(String enginePackage) {
            runOnUiThread(() -> requestTtsVoicesInternal(enginePackage));
        }

        @JavascriptInterface public void previewTts(String enginePackage, String voiceName) {
            runOnUiThread(() -> previewTtsInternal(enginePackage, voiceName));
        }

        @JavascriptInterface public void saveTtsChoice(String enginePackage, String voiceName) {
            String engine = enginePackage == null ? "" : enginePackage.trim();
            String voice = voiceName == null ? "" : voiceName.trim();
            localPrefs().edit().putString(PREF_TTS_ENGINE, engine).putString(PREF_TTS_VOICE, voice).apply();
            try {
                JSONObject choice = new JSONObject();
                choice.put("engine", engine);
                choice.put("voice", voice);
                js("window.ClearRoute && ClearRoute.onTtsChoiceSaved(" + choice + ")");
            } catch (Exception ignored) {}
        }

        @JavascriptInterface public void search(String query, boolean useLocationBias, long requestId) {
            Double lat = null, lon = null;
            if (useLocationBias && lastLocation != null) {
                lat = lastLocation.getLatitude();
                lon = lastLocation.getLongitude();
            }
            ApiClient.search(MainActivity.this, query, lat, lon, new ApiClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onSearchResults(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onSearchError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void searchSuggestions(String query, boolean useLocationBias, long requestId) {
            Double lat = null, lon = null;
            if (useLocationBias && lastLocation != null) {
                lat = lastLocation.getLatitude();
                lon = lastLocation.getLongitude();
            }
            ApiClient.searchSuggestions(MainActivity.this, query, lat, lon, new ApiClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onSearchSuggestions(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onSearchSuggestionError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void searchMapArea(String query, double north, double west,
                                                       double south, double east, long requestId) {
            ApiClient.searchMapArea(MainActivity.this, query, north, west, south, east, new ApiClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onMapAreaSearchResults(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onMapAreaSearchError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void searchHome(String query, long requestId) {
            Double lat = lastLocation == null ? null : lastLocation.getLatitude();
            Double lon = lastLocation == null ? null : lastLocation.getLongitude();
            ApiClient.search(MainActivity.this, query, lat, lon, new ApiClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onHomeSearchResults(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onHomeSearchError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void searchAlongRoute(String query, long requestId) {
            latestAlongRouteRequestId = requestId;
            JSONObject state = ActiveRouteStore.load(MainActivity.this);
            if (state == null) {
                js("ClearRoute.onAlongRouteError(" + requestId + ",'Start navigation before searching along the route')");
                return;
            }
            double lat = Double.isFinite(latestNavigationLat) ? latestNavigationLat : (lastLocation == null ? Double.NaN : lastLocation.getLatitude());
            double lon = Double.isFinite(latestNavigationLon) ? latestNavigationLon : (lastLocation == null ? Double.NaN : lastLocation.getLongitude());
            if (!Double.isFinite(lat) || !Double.isFinite(lon)) {
                js("ClearRoute.onAlongRouteError(" + requestId + ",'Waiting for your current location')");
                return;
            }
            String response = state.optJSONObject("response") == null ? "" : state.optJSONObject("response").toString();
            int routeIndex = state.optInt("routeIndex", 0);
            ApiClient.searchAlongRoute(MainActivity.this, response, routeIndex, lat, lon, query, new ApiClient.Callback() {
                @Override public void onSuccess(String json) {
                    if (requestId != latestAlongRouteRequestId) return;
                    js("ClearRoute.onAlongRouteResults(" + requestId + "," + json + ")");
                }
                @Override public void onError(String message) {
                    if (requestId != latestAlongRouteRequestId) return;
                    js("ClearRoute.onAlongRouteError(" + requestId + "," + JSONObject.quote(message) + ")");
                }
            });
        }

        @JavascriptInterface public void addAlongRouteStop(double stopLat, double stopLon, String stopName) {
            JSONObject state = ActiveRouteStore.load(MainActivity.this);
            if (state == null) {
                js("ClearRoute.onError('Navigation is no longer active')");
                return;
            }
            double originLat = Double.isFinite(latestNavigationLat) ? latestNavigationLat : (lastLocation == null ? Double.NaN : lastLocation.getLatitude());
            double originLon = Double.isFinite(latestNavigationLon) ? latestNavigationLon : (lastLocation == null ? Double.NaN : lastLocation.getLongitude());
            if (!Double.isFinite(originLat) || !Double.isFinite(originLon)) {
                js("ClearRoute.onError('Waiting for your current location')");
                return;
            }
            double finalLat = state.optDouble("destLat", 0);
            double finalLon = state.optDouble("destLon", 0);
            String travelMode = state.optString("mode", "drive");
            ApiClient.routeVia(MainActivity.this, originLat, originLon, stopLat, stopLon, finalLat, finalLon, travelMode,
                    new ApiClient.Callback() {
                        @Override public void onSuccess(String json) {
                            try {
                                JSONObject updated = ActiveRouteStore.load(MainActivity.this);
                                if (updated == null) return;
                                updated.put("routeIndex", 0);
                                updated.put("response", new JSONObject(json));
                                updated.put("hasWaypoint", true);
                                updated.put("waypointLat", stopLat);
                                updated.put("waypointLon", stopLon);
                                updated.put("waypointName", stopName == null ? "Stop" : stopName);
                                ActiveRouteStore.save(MainActivity.this, updated);
                                lastRouteResponse = json;
                                Intent reload = new Intent(MainActivity.this, NavigationService.class)
                                        .setAction(NavigationService.ACTION_RELOAD_ROUTE);
                                startService(reload);
                                js("ClearRoute.onAlongRouteStopAdded(" + JSONObject.quote(stopName == null ? "Stop" : stopName) + ")");
                            } catch (Exception e) {
                                js("ClearRoute.onError('Could not add that stop')");
                            }
                        }
                        @Override public void onError(String message) {
                            js("ClearRoute.onError(" + JSONObject.quote(message == null ? "Could not add that stop" : message) + ")");
                        }
                    });
        }

        @JavascriptInterface public void openShazam() {
            try {
                Intent launch = getPackageManager().getLaunchIntentForPackage("com.shazam.android");
                if (launch == null) {
                    js("ClearRoute.onShazamStatus(false,'Shazam is not installed on this phone')");
                    return;
                }
                launch.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                startActivity(launch);
                js("ClearRoute.onShazamStatus(true,'')");
            } catch (Exception e) {
                js("ClearRoute.onShazamStatus(false,'Could not open Shazam')");
            }
        }

        @JavascriptInterface public String getHome() {
            return localPrefs().getString(PREF_HOME, "");
        }

        @JavascriptInterface public void saveHome(String name, String address, double lat, double lon) {
            try {
                JSONObject home = new JSONObject();
                home.put("name", name == null || name.trim().isEmpty() ? "Home" : name.trim());
                home.put("address", address == null ? "" : address.trim());
                home.put("lat", lat);
                home.put("lon", lon);
                localPrefs().edit().putString(PREF_HOME, home.toString()).apply();
                js("ClearRoute.onHomeSaved(" + home + ")");
            } catch (Exception e) {
                js("ClearRoute.onError('Could not save Home')");
            }
        }

        @JavascriptInterface public void clearHome() {
            localPrefs().edit().remove(PREF_HOME).apply();
            js("ClearRoute.onHomeCleared()");
        }

        @JavascriptInterface public void cancelRouteRequests(long invalidationId) {
            latestRouteRequestId = invalidationId;
            TransitClient.cancelRouteWork();
        }

        private ApiClient.Callback routeCallback(long requestId) {
            return new ApiClient.Callback() {
                @Override public void onSuccess(String json) {
                    if (requestId != latestRouteRequestId) return;
                    lastRouteResponse = json;
                    js("ClearRoute.onRoute(" + json + ",0,false," + requestId + ")");
                }
                @Override public void onError(String message) {
                    if (requestId != latestRouteRequestId) return;
                    js("ClearRoute.onRouteError(" + requestId + "," + JSONObject.quote(message) + ")");
                }
            };
        }

        private void calculateRouteFromPoints(double originLat, double originLon, double destLat, double destLon, String mode, long requestId) {
            latestRouteRequestId = requestId;
            ApiClient.Callback callback = routeCallback(requestId);
            if ("transit".equals(mode)) {
                String appId = localPrefs().getString(PREF_TRANSPORTAPI_ID, "");
                String appKey = SecureStore.getSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY);
                String tflKey = SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
                String bodsKey = ""; // Server-only BODS: disable automatic on-device enrichment.
                String darwinUser = SecureStore.getSecret(MainActivity.this, SECRET_DARWIN_USER);
                TransitClient.route(MainActivity.this, originLat, originLon, destLat, destLon,
                        tflKey, bodsKey, darwinUser, "", appId, appKey, null, new TransitClient.Callback() {
                    @Override public void onSuccess(String json) { callback.onSuccess(json); }
                    @Override public void onUpdate(String json) {
                        if (requestId != latestRouteRequestId) return;
                        lastRouteResponse = json;
                        js("ClearRoute.onRouteLiveUpdate(" + json + "," + requestId + ")");
                    }
                    @Override public void onError(String message) { callback.onError(message); }
                    @Override public void onProgress(String stage, long elapsedMs) {
                        if (requestId != latestRouteRequestId) return;
                        js("ClearRoute.onTransitSearchProgress(" + requestId + "," + JSONObject.quote(stage) + "," + elapsedMs + ")");
                    }
                });
            } else {
                ApiClient.routeOptions(MainActivity.this, originLat, originLon, destLat, destLon, mode, callback);
            }
        }

        @JavascriptInterface public void calculateRoute(double destLat, double destLon, String mode, long requestId) {
            if (lastLocation == null || SystemClock.elapsedRealtime() - lastLocationElapsed > 30000L) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteNeedsLocation(" + requestId + ")");
                return;
            }
            calculateRouteFromPoints(lastLocation.getLatitude(), lastLocation.getLongitude(), destLat, destLon, mode, requestId);
        }

        @JavascriptInterface public void calculateRouteFrom(double originLat, double originLon, double destLat, double destLon, String mode, long requestId) {
            if (!Double.isFinite(originLat) || !Double.isFinite(originLon)) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteError(" + requestId + ",'Invalid start location')");
                return;
            }
            calculateRouteFromPoints(originLat, originLon, destLat, destLon, mode, requestId);
        }

        private void calculateRouteViaStopFromPoints(double originLat, double originLon, double destLat, double destLon,
                                                      double viaLat, double viaLon, String mode, long requestId) {
            latestRouteRequestId = requestId;
            ApiClient.routeVia(MainActivity.this, originLat, originLon,
                    viaLat, viaLon, destLat, destLon, mode, new ApiClient.Callback() {
                @Override public void onSuccess(String json) {
                    if (requestId != latestRouteRequestId) return;
                    lastRouteResponse = json;
                    js("ClearRoute.onRoute(" + json + ",0,false," + requestId + ")");
                }
                @Override public void onError(String message) {
                    if (requestId != latestRouteRequestId) return;
                    js("ClearRoute.onRouteError(" + requestId + "," + JSONObject.quote(message) + ")");
                }
            });
        }

        @JavascriptInterface public void calculateRouteViaStop(double destLat, double destLon, double viaLat, double viaLon, String mode, long requestId) {
            if (lastLocation == null || SystemClock.elapsedRealtime() - lastLocationElapsed > 30000L) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteNeedsLocation(" + requestId + ")");
                return;
            }
            calculateRouteViaStopFromPoints(lastLocation.getLatitude(), lastLocation.getLongitude(), destLat, destLon, viaLat, viaLon, mode, requestId);
        }

        @JavascriptInterface public void calculateRouteViaStopFrom(double originLat, double originLon, double destLat, double destLon,
                                                                    double viaLat, double viaLon, String mode, long requestId) {
            if (!Double.isFinite(originLat) || !Double.isFinite(originLon)) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteError(" + requestId + ",'Invalid start location')");
                return;
            }
            calculateRouteViaStopFromPoints(originLat, originLon, destLat, destLon, viaLat, viaLon, mode, requestId);
        }

        @JavascriptInterface public void prepareTransitDestination(double lat, double lon) {
            TransitClient.prepareServerRegion(MainActivity.this, lat, lon, "destination");
        }

        @JavascriptInterface public void preloadTransitArea(String query, long requestId) {
            final String q = query == null ? "" : query.trim();
            if (q.length() < 2) { js("ClearRoute.onTransitPreloadAreaResult(false,'Enter a town or postcode.'," + requestId + ")"); return; }
            ApiClient.search(MainActivity.this, q, null, null, new ApiClient.Callback() {
                @Override public void onSuccess(String json) {
                    try {
                        JSONObject root = new JSONObject(json); JSONArray results = root.optJSONArray("results");
                        JSONObject first = results == null || results.length() == 0 ? null : results.optJSONObject(0);
                        JSONObject pos = first == null ? null : first.optJSONObject("position");
                        if (pos == null) throw new Exception("No matching area found.");
                        double lat = pos.optDouble("lat", Double.NaN), lon = pos.optDouble("lon", Double.NaN);
                        if (!Double.isFinite(lat) || !Double.isFinite(lon)) throw new Exception("No matching area found.");
                        TransitClient.prepareServerRegion(MainActivity.this, lat, lon, "manual");
                        js("ClearRoute.onTransitPreloadAreaResult(true," + JSONObject.quote(q) + "," + requestId + ")");
                    } catch (Exception e) { js("ClearRoute.onTransitPreloadAreaResult(false," + JSONObject.quote(e.getMessage() == null ? "Could not find that area." : e.getMessage()) + "," + requestId + ")"); }
                }
                @Override public void onError(String message) { js("ClearRoute.onTransitPreloadAreaResult(false," + JSONObject.quote(message == null ? "Could not find that area." : message) + "," + requestId + ")"); }
            });
        }

        @JavascriptInterface public boolean isDailyTransitPreloadEnabled() {
            return localPrefs().getBoolean(TransitPreloadReceiver.PREF_ENABLED, true);
        }

        @JavascriptInterface public void setTransitNavigationActive(boolean active) {
            localPrefs().edit().putBoolean(TransitPreloadReceiver.PREF_TRANSIT_NAV_ACTIVE, active).apply();
        }

        @JavascriptInterface public boolean hasBackgroundLocationPermission() {
            return Build.VERSION.SDK_INT < 29 || checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface public void setDailyTransitPreloadEnabled(boolean enabled) {
            localPrefs().edit().putBoolean(TransitPreloadReceiver.PREF_ENABLED, enabled).apply();
            if (!enabled) { TransitPreloadReceiver.cancel(MainActivity.this); return; }
            TransitPreloadReceiver.schedule(MainActivity.this);
            if (Build.VERSION.SDK_INT >= 29 && checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED)
                runOnUiThread(() -> requestPermissions(new String[]{Manifest.permission.ACCESS_BACKGROUND_LOCATION}, REQ_BACKGROUND_LOCATION));
        }

        private void calculateTransitRouteWithStopsFromPoints(double originLat, double originLon, double destLat, double destLon,
                                                              String stopsJson, String settingsJson, long requestId) {
            latestRouteRequestId = requestId;
            try {
                JSONArray viaStops = stopsJson == null || stopsJson.trim().isEmpty() ? new JSONArray() : new JSONArray(stopsJson);
                JSONObject transitSettings = settingsJson == null || settingsJson.trim().isEmpty() ? new JSONObject() : new JSONObject(settingsJson);
                String appId = localPrefs().getString(PREF_TRANSPORTAPI_ID, "");
                String appKey = SecureStore.getSecret(MainActivity.this, SECRET_TRANSPORTAPI_KEY);
                String tflKey = SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
                String bodsKey = ""; // Server-only BODS: disable automatic on-device enrichment.
                String darwinUser = SecureStore.getSecret(MainActivity.this, SECRET_DARWIN_USER);
                TransitClient.routeWithStops(MainActivity.this, originLat, originLon, destLat, destLon, viaStops,
                        tflKey, bodsKey, darwinUser, "", appId, appKey, transitSettings, new TransitClient.Callback() {
                    @Override public void onSuccess(String json) {
                        if (requestId != latestRouteRequestId) return;
                        lastRouteResponse = json;
                        js("ClearRoute.onRoute(" + json + ",0,false," + requestId + ")");
                    }
                    @Override public void onUpdate(String json) {
                        if (requestId != latestRouteRequestId) return;
                        lastRouteResponse = json;
                        js("ClearRoute.onRouteLiveUpdate(" + json + "," + requestId + ")");
                    }
                    @Override public void onError(String message) {
                        if (requestId != latestRouteRequestId) return;
                        js("ClearRoute.onRouteError(" + requestId + "," + JSONObject.quote(message) + ")");
                    }
                    @Override public void onProgress(String stage, long elapsedMs) {
                        if (requestId != latestRouteRequestId) return;
                        js("ClearRoute.onTransitSearchProgress(" + requestId + "," + JSONObject.quote(stage) + "," + elapsedMs + ")");
                    }
                });
            } catch (Exception e) {
                if (requestId != latestRouteRequestId) return;
                js("ClearRoute.onRouteError(" + requestId + "," + JSONObject.quote("Could not read the added public-transport stops") + ")");
            }
        }

        @JavascriptInterface public void calculateTransitRouteWithStops(double destLat, double destLon, String stopsJson, String settingsJson, long requestId) {
            if (lastLocation == null || SystemClock.elapsedRealtime() - lastLocationElapsed > 30000L) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteNeedsLocation(" + requestId + ")");
                return;
            }
            calculateTransitRouteWithStopsFromPoints(lastLocation.getLatitude(), lastLocation.getLongitude(), destLat, destLon, stopsJson, settingsJson, requestId);
        }

        @JavascriptInterface public void calculateTransitRouteWithStopsFrom(double originLat, double originLon, double destLat, double destLon,
                                                                             String stopsJson, String settingsJson, long requestId) {
            if (!Double.isFinite(originLat) || !Double.isFinite(originLon)) {
                latestRouteRequestId = requestId;
                js("ClearRoute.onRouteError(" + requestId + ",'Invalid start location')");
                return;
            }
            calculateTransitRouteWithStopsFromPoints(originLat, originLon, destLat, destLon, stopsJson, settingsJson, requestId);
        }

        @JavascriptInterface public void prepareTransitData(double lat, double lon) {
            TransitClient.prepareLocalTimetable(MainActivity.this, lat, lon);
        }

        @JavascriptInterface public void lookupBusRoute(String line, long requestId) {
            if (lastLocation == null || SystemClock.elapsedRealtime() - lastLocationElapsed > 60000L) {
                js("ClearRoute.onBusRouteError(" + requestId + ",'Current location is needed to find the relevant bus service.')");
                return;
            }
            String tflKey = SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
            String bodsKey = SecureStore.getSecret(MainActivity.this, SECRET_BODS_KEY);
            TransitClient.lookupBusLine(MainActivity.this, lastLocation.getLatitude(), lastLocation.getLongitude(), line, tflKey, bodsKey, new TransitClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onBusRoute(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onBusRouteError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void lookupBusRouteNear(String line, double lat, double lon, long requestId) {
            String tflKey = SecureStore.getSecret(MainActivity.this, SECRET_TFL_KEY);
            String bodsKey = SecureStore.getSecret(MainActivity.this, SECRET_BODS_KEY);
            TransitClient.lookupBusLine(MainActivity.this, lat, lon, line, tflKey, bodsKey, new TransitClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onBusRoute(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onBusRouteError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void lookupBusStop(String stopId, double lat, double lon, long requestId) {
            TransitClient.lookupBusStop(MainActivity.this, stopId, lat, lon, new TransitClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onBusStop(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onBusStopError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void loadBusLiveVehicles(String line, double lat, double lon, long requestId) {
            TransitClient.lookupBusLive(MainActivity.this, lat, lon, line, new TransitClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onBusLive(" + json + "," + requestId + ")"); }
                @Override public void onError(String message) { js("ClearRoute.onBusLiveError(" + requestId + "," + JSONObject.quote(message) + ")"); }
            });
        }

        @JavascriptInterface public void requestPlaceDetails(String name, double lat, double lon) {
            ApiClient.search(MainActivity.this, name == null ? "" : name, lat, lon, new ApiClient.Callback() {
                @Override public void onSuccess(String json) { js("ClearRoute.onPlaceDetails(" + json + "," + lat + "," + lon + ")"); }
                @Override public void onError(String message) { }
            });
        }

        @JavascriptInterface public void startTransitNavigation(int routeIndex) {
            if (lastRouteResponse == null || lastRouteResponse.isEmpty()) {
                js("ClearRoute.onError('Calculate a public-transport journey first')");
                return;
            }
            try {
                JSONObject state = new JSONObject();
                state.put("routeIndex", routeIndex);
                state.put("mode", "transit");
                state.put("transitLegIndex", 0);
                state.put("response", new JSONObject(lastRouteResponse));
                ActiveRouteStore.save(MainActivity.this, state);
                localPrefs().edit().putBoolean(TransitPreloadReceiver.PREF_TRANSIT_NAV_ACTIVE, true).apply();
                runOnUiThread(MainActivity.this::requestNotificationPermission);
                stopLocationUpdates();
                Intent service = new Intent(MainActivity.this, TransitNavigationService.class);
                if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
            } catch (Exception e) {
                Log.e("OpenRoadTransitNav", "Could not start transit navigation", e);
                js("ClearRoute.onError('Could not start public-transport navigation')");
            }
        }

        @JavascriptInterface public void stopTransitNavigation() {
            try {
                Intent stop = new Intent(MainActivity.this, TransitNavigationService.class).setAction(TransitNavigationService.ACTION_STOP);
                startService(stop);
            } catch (Exception e) {
                localPrefs().edit().putBoolean(TransitPreloadReceiver.PREF_TRANSIT_NAV_ACTIVE, false).apply();
                ActiveRouteStore.clear(MainActivity.this);
                js("ClearRoute.onNavigationStopped('stopped')");
            }
        }

        @JavascriptInterface public void startNavigation(int routeIndex, double destLat, double destLon, String mode) {
            startNavigationWithStops(routeIndex, destLat, destLon, mode, "[]");
        }

        @JavascriptInterface public void startNavigationWithStops(int routeIndex, double destLat, double destLon, String mode, String stopsJson) {
            if ("transit".equals(mode)) {
                js("ClearRoute.onError('Public-transport journeys use the Journey/Steps view rather than driving-style turn-by-turn navigation')");
                return;
            }
            if (lastRouteResponse == null || lastRouteResponse.isEmpty()) {
                js("ClearRoute.onError('Calculate a route first')");
                return;
            }
            try {
                JSONObject state = new JSONObject();
                state.put("routeIndex", routeIndex);
                state.put("destLat", destLat);
                state.put("destLon", destLon);
                state.put("mode", mode);
                state.put("response", new JSONObject(lastRouteResponse));
                JSONArray via = new JSONArray(stopsJson == null ? "[]" : stopsJson);
                if (via.length() > 0) {
                    JSONObject stop = via.getJSONObject(0);
                    double lat = stop.getDouble("lat"), lon = stop.getDouble("lon");
                    if (!Double.isFinite(lat) || !Double.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
                        throw new IllegalArgumentException("Invalid navigation stop");
                    state.put("hasWaypoint", true);
                    state.put("waypointLat", lat);
                    state.put("waypointLon", lon);
                    state.put("waypointName", stop.optString("name", "Stop"));
                }
                ActiveRouteStore.save(MainActivity.this, state);
                Intent service = new Intent(MainActivity.this, NavigationService.class)
                        .putExtra("routeIndex", routeIndex)
                        .putExtra("destLat", destLat)
                        .putExtra("destLon", destLon)
                        .putExtra("mode", mode);
                runOnUiThread(MainActivity.this::requestNotificationPermission);
                stopLocationUpdates();
                if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
                // JavascriptInterface methods run on the WebView bridge thread. Window flags are
                // UI operations and must be changed on Android's main thread; otherwise navigation
                // can start successfully and then falsely report "Could not start navigation".
                runOnUiThread(() -> {
                    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                    js("ClearRoute.onNavigationStarted()");
                });
            } catch (Exception e) {
                Log.e("ClearRouteNavigation", "Could not start navigation", e);
                js("ClearRoute.onError('Could not start navigation')");
            }
        }

        @JavascriptInterface public void stopNavigation() {
            try {
                Intent stop = new Intent(MainActivity.this, NavigationService.class).setAction(NavigationService.ACTION_STOP);
                startService(stop);
            } catch (Exception e) {
                ActiveRouteStore.clear(MainActivity.this);
                runOnUiThread(() -> {
                    startLocationUpdates();
                    js("ClearRoute.onNavigationStopped('stopped')");
                });
            }
        }

        @JavascriptInterface public void forceReroute() {
            try {
                Intent action = new Intent(MainActivity.this, NavigationService.class)
                        .setAction(NavigationService.ACTION_FORCE_REROUTE);
                startService(action);
            } catch (Exception e) {
                js("ClearRoute.onError('Could not request a reroute')");
            }
        }

        @JavascriptInterface public void avoidRoadAhead() {
            try {
                Intent action = new Intent(MainActivity.this, NavigationService.class)
                        .setAction(NavigationService.ACTION_AVOID_AHEAD);
                startService(action);
            } catch (Exception e) {
                js("ClearRoute.onError('Could not avoid the road ahead')");
            }
        }

        @JavascriptInterface public String getFavourites() {
            return getPreferences(MODE_PRIVATE).getString("favourites", "[]");
        }

        @JavascriptInterface public void saveFavourite(String name, double lat, double lon) {
            try {
                JSONArray existing = new JSONArray(getFavourites());
                JSONArray arr = new JSONArray();
                // Keep the local list tidy: replace a near-identical saved place rather than
                // accumulating duplicates, and cap the list for this single-user app.
                for (int i = 0; i < existing.length(); i++) {
                    JSONObject item = existing.optJSONObject(i);
                    if (item == null) continue;
                    double dLat = item.optDouble("lat", 999) - lat;
                    double dLon = item.optDouble("lon", 999) - lon;
                    if (Math.hypot(dLat, dLon) < 0.00015) continue;
                    if (arr.length() < 29) arr.put(item);
                }
                JSONObject f = new JSONObject();
                f.put("name", name == null || name.trim().isEmpty() ? "Saved place" : name.trim());
                f.put("lat", lat); f.put("lon", lon);
                JSONArray output = new JSONArray(); output.put(f);
                for (int i = 0; i < arr.length(); i++) output.put(arr.get(i));
                getPreferences(MODE_PRIVATE).edit().putString("favourites", output.toString()).apply();
            } catch (Exception ignored) {}
        }

        @JavascriptInterface public void removeFavourite(int index) {
            try {
                JSONArray existing = new JSONArray(getFavourites());
                JSONArray output = new JSONArray();
                for (int i = 0; i < existing.length(); i++) if (i != index) output.put(existing.get(i));
                getPreferences(MODE_PRIVATE).edit().putString("favourites", output.toString()).apply();
            } catch (Exception ignored) {}
        }

        @JavascriptInterface public void renameFavourite(int index, String name) {
            try {
                String clean = name == null ? "" : name.trim();
                if (clean.isEmpty()) return;
                JSONArray existing = new JSONArray(getFavourites());
                JSONObject item = existing.optJSONObject(index);
                if (item == null) return;
                item.put("name", clean);
                getPreferences(MODE_PRIVATE).edit().putString("favourites", existing.toString()).apply();
            } catch (Exception ignored) {}
        }

        @JavascriptInterface public boolean hasActiveRoute() {
            return ActiveRouteStore.exists(MainActivity.this);
        }

        @JavascriptInterface public void restoreActiveRoute() {
            loadActiveRouteIntoWebView(true);
        }
    }

    @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
    @Override public void onProviderEnabled(String provider) { startLocationUpdates(); }
    @Override public void onProviderDisabled(String provider) {
        if (webReady && !isLocationEnabled()) js("window.ClearRoute && ClearRoute.onLocationStatus('disabled')");
    }
}
