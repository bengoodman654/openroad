package uk.co.bengoodman.clearroute;

import android.content.Context;
import android.net.Uri;
import android.os.SystemClock;
import android.util.Log;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;
import org.xmlpull.v1.XmlPullParser;
import org.xmlpull.v1.XmlPullParserFactory;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.StringReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Public-transport broker for OpenRoad.
 *
 * Priority is deliberately "official data first":
 *  - TfL Journey Planner for journeys wholly inside Greater London.
 *  - DfT/BODS GTFS is routed locally for English bus journeys outside London.
 *  - TransportAPI is optional fallback only and is disabled by default.
 *  - BODS SIRI-VM is used to confirm fresh live English bus vehicle data.
 *  - National Rail Darwin LDB is used to replace scheduled rail times with live predictions.
 *  - NaPTAN stop areas encountered in routes are cached locally from the DfT API.
 *
 * Live labels are only added when the upstream feed is genuinely live and recent. Scheduled
 * information is never promoted to "live" merely because it was fetched over the network.
 */
public final class TransitClient {
    public interface Callback {
        void onSuccess(String json);
        void onError(String message);
        default void onUpdate(String json) {}
        default void onProgress(String stage, long elapsedMs) {}
    }

    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(3);
    private static final ExecutorService PRELOAD_EXECUTOR = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OpenRoad-transit-preload"); t.setDaemon(true); return t;
    });
    // A separate thread ensures the foreground deadline still fires if the GTFS parser is busy.
    private static final ScheduledExecutorService WATCHDOG = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "OpenRoad-transit-deadline"); t.setDaemon(true); return t;
    });
    private static final long FOREGROUND_DEADLINE_MS = 18_500L;
    private static final String TIMING_TAG = "OpenRoadTransit";
    private static final AtomicReference<ScheduledFuture<?>> ACTIVE_DEADLINE = new AtomicReference<>();
    private static final Object ROUTE_LIFECYCLE_LOCK = new Object();
    private static final AtomicLong ROUTE_GENERATION = new AtomicLong(0L);
    private static final AtomicReference<Future<?>> ACTIVE_ROUTE_TASK = new AtomicReference<>();
    private static final long NAPTAN_MAX_AGE_MS = 7L * 24L * 60L * 60L * 1000L;
    private static final long BODS_FRESH_MS = 3L * 60L * 1000L;
    private static final long BODS_LAST_KNOWN_MS = 15L * 60L * 1000L;

    private TransitClient() {}
    public static void cancelRouteWork() {
        synchronized (ROUTE_LIFECYCLE_LOCK) {
            ROUTE_GENERATION.incrementAndGet();
            ScheduledFuture<?> deadline = ACTIVE_DEADLINE.getAndSet(null);
            if (deadline != null) deadline.cancel(false);
            Future<?> f = ACTIVE_ROUTE_TASK.getAndSet(null);
            if (f != null) f.cancel(true);
        }
    }
    private static long beginRouteWork() {
        synchronized (ROUTE_LIFECYCLE_LOCK) {
            cancelRouteWork();
            return ROUTE_GENERATION.get();
        }
    }
    private static void rememberRouteTask(long token, Future<?> future) {
        synchronized (ROUTE_LIFECYCLE_LOCK) {
            // A newer search may have started between submit() and this registration.
            // An older job must never replace (and cancel) the newer job.
            if (token != ROUTE_GENERATION.get()) { future.cancel(true); return; }
            Future<?> previous = ACTIVE_ROUTE_TASK.getAndSet(future);
            if (previous != null && previous != future) previous.cancel(true);
        }
    }
    private static boolean routeWorkCancelled(long token) { return token != ROUTE_GENERATION.get() || Thread.currentThread().isInterrupted(); }
    /** Time-boxes the full pipeline, including server lookup, local fallback and enrichment.
     * The gate makes a timeout and a result mutually exclusive; late callbacks are ignored. */
    private static Callback budgeted(long token, Callback callback, TransitSearchGate gate, long startMs) {
        return new Callback() {
            @Override public void onSuccess(String json) {
                synchronized (gate) {
                    if (token != ROUTE_GENERATION.get() || !gate.first()) return;
                    Log.i(TIMING_TAG, "first_result_ms=" + (SystemClock.elapsedRealtime() - startMs));
                    callback.onSuccess(json);
                }
            }
            @Override public void onUpdate(String json) {
                synchronized (gate) {
                    if (token == ROUTE_GENERATION.get() && gate.update()) callback.onUpdate(json);
                }
            }
            @Override public void onError(String message) {
                synchronized (gate) {
                    if (token != ROUTE_GENERATION.get() || !gate.fail()) return;
                    Log.w(TIMING_TAG, "route_failed_ms=" + (SystemClock.elapsedRealtime() - startMs));
                    callback.onError(message);
                }
            }
            @Override public void onProgress(String stage, long elapsedMs) {
                synchronized (gate) {
                    if (token == ROUTE_GENERATION.get() && gate.progress()) callback.onProgress(stage, elapsedMs);
                }
            }
        };
    }
    private static ScheduledFuture<?> armDeadline(long token, TransitSearchGate gate, Callback original, long startMs) {
        synchronized (ROUTE_LIFECYCLE_LOCK) {
            if (token != ROUTE_GENERATION.get()) return null;
        ScheduledFuture<?> timeout = WATCHDOG.schedule(() -> {
            if (token != ROUTE_GENERATION.get()) return;
            synchronized (gate) {
                boolean noResult = gate.expire();
                Log.w(TIMING_TAG, "foreground_deadline_ms=" + (SystemClock.elapsedRealtime() - startMs)
                        + " initial_result=" + !noResult);
                if (noResult) original.onError("No complete public-transport route was found within 20 seconds. "
                        + "Try again or choose a different journey. A timetable may still be preparing.");
            }
            synchronized (ROUTE_LIFECYCLE_LOCK) {
                if (token == ROUTE_GENERATION.get()) {
                    Future<?> f = ACTIVE_ROUTE_TASK.get();
                    if (f != null) f.cancel(true);
                }
            }
        }, FOREGROUND_DEADLINE_MS, TimeUnit.MILLISECONDS);
        ScheduledFuture<?> old = ACTIVE_DEADLINE.getAndSet(timeout);
        if (old != null) old.cancel(false);
        return timeout;
        }
    }
    private static void completeSearch(long token, TransitSearchGate gate, ScheduledFuture<?> timeout, long startMs) {
        if (token == ROUTE_GENERATION.get()) {
            if (timeout != null) {
                timeout.cancel(false);
                ACTIVE_DEADLINE.compareAndSet(timeout, null);
            }
            synchronized (gate) { gate.complete(); }
            Log.i(TIMING_TAG, "pipeline_end_ms=" + (SystemClock.elapsedRealtime() - startMs));
        }
    }
    private static void progress(Callback callback, String stage, long startMs) {
        callback.onProgress(stage, SystemClock.elapsedRealtime() - startMs);
    }
    private static JSONObject copySettings(JSONObject settings) {
        try { return settings == null ? new JSONObject() : new JSONObject(settings.toString()); }
        catch (Exception ignored) { return new JSONObject(); }
    }

    private static boolean canUsePrivateServer(Context context, double originLat, double originLon, double destLat, double destLon) {
        return !insideGreaterLondon(originLat, originLon) && !insideGreaterLondon(destLat, destLon)
                && OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
    }

    public static void prepareServerRegion(Context context, double lat, double lon, String reason) {
        if (!OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL)) return;
        // Regional preparation only needs an approximate area. Avoid sending precise GPS coordinates
        // for background/destination preload requests when a ~1 km grid point is sufficient.
        final double coarseLat = Math.round(lat * 100.0) / 100.0;
        final double coarseLon = Math.round(lon * 100.0) / 100.0;
        PRELOAD_EXECUTOR.execute(() -> { try { OpenRoadServerClient.prepareRegion(context, coarseLat, coarseLon, reason, BuildConfig.BUNDLED_OPENROAD_SERVER_URL); } catch (Exception ignored) {} });
    }


    public static void prepareLocalTimetable(Context context, double lat, double lon) {
        // When the private pre-indexed server is configured, do not start the expensive regional
        // GTFS download/parser on the phone merely because Public transport was selected.
        if (OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL)) return;
        PRELOAD_EXECUTOR.execute(() -> {
            try { BodsJourneyPlanner.prepare(context, lat, lon); }
            catch (Exception ignored) {}
        });
    }

    public static void route(Context context,
                             double originLat, double originLon,
                             double destLat, double destLon,
                             String tflKey, String bodsKey,
                             String darwinUser, String darwinPassword,
                             String transportId, String transportKey, JSONObject settings,
                             Callback callback) {
        final long token = beginRouteWork();
        final long startMs = SystemClock.elapsedRealtime();
        final TransitSearchGate gate = new TransitSearchGate();
        final Callback guarded = budgeted(token, callback, gate, startMs);
        final ScheduledFuture<?> timeout = armDeadline(token, gate, callback, startMs);
        if (timeout == null) return; // a newer search already superseded this one
        Future<?> future = EXECUTOR.submit(() -> {
            try {
            if (routeWorkCancelled(token)) return;
            progress(guarded, "Searching public transport timetables…", startMs);
            try {
                JSONObject initialSettings=copySettings(settings);
                boolean staged=canUsePrivateServer(context,originLat,originLon,destLat,destLon);
                if(staged)initialSettings.put("serverPhase","fast");
                JSONObject initial = routeOnce(context, originLat, originLon, destLat, destLon, tflKey, bodsKey, darwinUser, darwinPassword, transportId, transportKey, initialSettings);
                if(routeWorkCancelled(token))return;
                guarded.onSuccess(initial.toString());
                progress(guarded, "Checking connections and live departures…", startMs);
                try {
                    JSONObject enriched = new JSONObject(initial.toString());
                    if(routeWorkCancelled(token))return;
                    if (enrichWalkingGeometry(context, enriched, 0, 1) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    if(staged){
                        JSONObject fullSettings=copySettings(settings);fullSettings.put("serverPhase","full");
                        JSONObject full=routeOnce(context,originLat,originLon,destLat,destLon,tflKey,bodsKey,darwinUser,darwinPassword,transportId,transportKey,fullSettings);
                        if(routeWorkCancelled(token))return;
                        enriched=full;enrichWalkingGeometry(context,enriched,0,1);
                        if(!routeWorkCancelled(token))guarded.onUpdate(enriched.toString());
                    }
                    if(routeWorkCancelled(token))return;
                    if (BodsJourneyPlanner.enrichGeometry(context, enriched) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    String beforeLive = enriched.toString();
                    enrichOfficialLive(context, enriched, bodsKey, darwinUser, darwinPassword);
                    if(routeWorkCancelled(token))return;
                    if (!beforeLive.equals(enriched.toString())) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    if (enrichWalkingGeometry(context, enriched, 1, enriched.optJSONArray("routes") == null ? 1 : enriched.optJSONArray("routes").length()) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                } catch (Exception ignored) {}
            }
            catch (Exception e) { if(!routeWorkCancelled(token)) guarded.onError(e.getMessage() == null ? "Public transport route failed" : e.getMessage()); }
            } finally { completeSearch(token, gate, timeout, startMs); }
        });
        rememberRouteTask(token, future);
    }

    public static void routeWithStops(Context context,
                                      double originLat, double originLon,
                                      double destLat, double destLon, JSONArray viaStops,
                                      String tflKey, String bodsKey,
                                      String darwinUser, String darwinPassword,
                                      String transportId, String transportKey, JSONObject settings,
                                      Callback callback) {
        final long token = beginRouteWork();
        final long startMs = SystemClock.elapsedRealtime();
        final TransitSearchGate gate = new TransitSearchGate();
        final Callback guarded = budgeted(token, callback, gate, startMs);
        final ScheduledFuture<?> timeout = armDeadline(token, gate, callback, startMs);
        if (timeout == null) return; // a newer search already superseded this one
        Future<?> future = EXECUTOR.submit(() -> {
            try {
            if (routeWorkCancelled(token)) return;
            progress(guarded, "Searching public transport timetables…", startMs);
            try {
                if (viaStops == null || viaStops.length() == 0) {
                    JSONObject initialSettings=copySettings(settings);boolean staged=canUsePrivateServer(context,originLat,originLon,destLat,destLon);if(staged)initialSettings.put("serverPhase","fast");
                    JSONObject initial = routeOnce(context, originLat, originLon, destLat, destLon, tflKey, bodsKey, darwinUser, darwinPassword, transportId, transportKey, initialSettings);
                    if(routeWorkCancelled(token))return;
                    guarded.onSuccess(initial.toString());
                progress(guarded, "Checking connections and live departures…", startMs);
                    try {
                        JSONObject enriched = new JSONObject(initial.toString());
                        if(routeWorkCancelled(token))return;
                        if (enrichWalkingGeometry(context, enriched, 0, 1) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                        if(routeWorkCancelled(token))return;
                        if(staged){
                            JSONObject fullSettings=copySettings(settings);fullSettings.put("serverPhase","full");
                            JSONObject full=routeOnce(context,originLat,originLon,destLat,destLon,tflKey,bodsKey,darwinUser,darwinPassword,transportId,transportKey,fullSettings);
                            if(routeWorkCancelled(token))return;
                            enriched=full;enrichWalkingGeometry(context,enriched,0,1);
                            if(!routeWorkCancelled(token))guarded.onUpdate(enriched.toString());
                        }
                        if(routeWorkCancelled(token))return;
                        if (BodsJourneyPlanner.enrichGeometry(context, enriched) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                        if(routeWorkCancelled(token))return;
                        String beforeLive = enriched.toString();
                        enrichOfficialLive(context, enriched, bodsKey, darwinUser, darwinPassword);
                        if(routeWorkCancelled(token))return;
                        if (!beforeLive.equals(enriched.toString())) guarded.onUpdate(enriched.toString());
                        if(routeWorkCancelled(token))return;
                        if (enrichWalkingGeometry(context, enriched, 1, enriched.optJSONArray("routes") == null ? 1 : enriched.optJSONArray("routes").length()) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                    } catch (Exception ignored) {}
                    return;
                }
                List<double[]> points = new ArrayList<>();
                points.add(new double[]{originLat, originLon});
                for (int i = 0; i < viaStops.length() && i < 5; i++) {
                    JSONObject v = viaStops.optJSONObject(i); if (v == null) continue;
                    double lat = v.optDouble("lat", Double.NaN), lon = v.optDouble("lon", Double.NaN);
                    if (Double.isFinite(lat) && Double.isFinite(lon)) points.add(new double[]{lat, lon});
                }
                points.add(new double[]{destLat, destLon});
                List<JSONObject> segmentResponses = new ArrayList<>();
                boolean hasStagedSegment = false;
                for (int i = 0; i < points.size() - 1; i++) {
                    if(routeWorkCancelled(token))return;
                    double[] a = points.get(i), b = points.get(i + 1);
                    JSONObject segmentSettings = copySettings(settings);
                    if (canUsePrivateServer(context, a[0], a[1], b[0], b[1])) {
                        segmentSettings.put("serverPhase", "fast");
                        hasStagedSegment = true;
                    }
                    segmentResponses.add(routeOnce(context, a[0], a[1], b[0], b[1], tflKey, bodsKey, darwinUser, darwinPassword, transportId, transportKey, segmentSettings));
                    if(routeWorkCancelled(token))return;
                }
                JSONObject initial = combineSegmentJourneys(segmentResponses, viaStops);
                if(routeWorkCancelled(token))return;
                guarded.onSuccess(initial.toString());
                progress(guarded, "Checking connections and live departures…", startMs);
                try {
                    JSONObject enriched = new JSONObject(initial.toString());
                    if(routeWorkCancelled(token))return;
                    if (enrichWalkingGeometry(context, enriched, 0, 1) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    if (hasStagedSegment) {
                        List<JSONObject> fullSegments = new ArrayList<>();
                        for (int i = 0; i < points.size() - 1; i++) {
                            if(routeWorkCancelled(token))return;
                            double[] a = points.get(i), b = points.get(i + 1);
                            if (canUsePrivateServer(context, a[0], a[1], b[0], b[1])) {
                                JSONObject fullSettings = copySettings(settings);fullSettings.put("serverPhase", "full");
                                fullSegments.add(routeOnce(context, a[0], a[1], b[0], b[1], tflKey, bodsKey, darwinUser, darwinPassword, transportId, transportKey, fullSettings));
                            } else fullSegments.add(segmentResponses.get(i));
                        }
                        if(routeWorkCancelled(token))return;
                        enriched = combineSegmentJourneys(fullSegments, viaStops);
                        enrichWalkingGeometry(context, enriched, 0, 1);
                        if(!routeWorkCancelled(token))guarded.onUpdate(enriched.toString());
                    }
                    if(routeWorkCancelled(token))return;
                    if (BodsJourneyPlanner.enrichGeometry(context, enriched) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    String beforeLive = enriched.toString();
                    enrichOfficialLive(context, enriched, bodsKey, darwinUser, darwinPassword);
                    if(routeWorkCancelled(token))return;
                    if (!beforeLive.equals(enriched.toString())) guarded.onUpdate(enriched.toString());
                    if(routeWorkCancelled(token))return;
                    if (enrichWalkingGeometry(context, enriched, 1, enriched.optJSONArray("routes") == null ? 1 : enriched.optJSONArray("routes").length()) && !routeWorkCancelled(token)) guarded.onUpdate(enriched.toString());
                } catch (Exception ignored) {}
            } catch (Exception e) { if(!routeWorkCancelled(token)) guarded.onError(e.getMessage() == null ? "Public transport route failed" : e.getMessage()); }
            } finally { completeSearch(token, gate, timeout, startMs); }
        });
        rememberRouteTask(token, future);
    }

    private static JSONObject routeOnce(Context context, double originLat, double originLon, double destLat, double destLon,
                                        String tflKey, String bodsKey, String darwinUser, String darwinPassword,
                                        String transportId, String transportKey, JSONObject settings) throws Exception {
        JSONObject safeSettings = settings == null ? new JSONObject() : settings;
        boolean allowTransportApiFallback = safeSettings.optBoolean("transportApiFallback", false);
        Exception officialFailure = null;

        // London has a genuine official journey planner, so use it directly first.
        if (insideGreaterLondon(originLat, originLon) && insideGreaterLondon(destLat, destLon)) {
            long providerStart = SystemClock.elapsedRealtime();
            try {
                JSONObject result = new JSONObject(requestTflJourney(originLat, originLon, destLat, destLon, tflKey, safeSettings));
                Log.i(TIMING_TAG, "provider=tfl outcome=success ms=" + (SystemClock.elapsedRealtime()-providerStart));
                return result;
            } catch (Exception e) {
                Log.w(TIMING_TAG, "provider=tfl outcome=failed ms=" + (SystemClock.elapsedRealtime()-providerStart));
                officialFailure = e;
            }
        } else {
            JSONObject allowedModes = safeSettings.optJSONObject("modes");
            boolean busEnabled = allowedModes == null || allowedModes.optBoolean("bus",true);
            boolean railEnabled = allowedModes == null || allowedModes.optBoolean("train",true);
            if (!busEnabled && !railEnabled)
                throw new Exception("Enable buses or trains in Public transport settings.");
            // For a region-spanning journey, attempt rail before local-bus routing.
            // This is a signed request to the owner's server, never a feed download
            // or an RDM credential in the Android app.
            boolean pairedForRail=OpenRoadServerClient.configured(context,BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
            double directMetres=distanceMetres(originLat,originLon,destLat,destLon);
            JSONObject scheduledRail=null;
            if(railEnabled && pairedForRail && (directMetres>=6500 || !busEnabled)){
                try{
                    scheduledRail=OpenRoadServerClient.railJourneys(context,originLat,originLon,destLat,destLon,
                            BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                }catch(Exception ignored){
                    // A missing, stale or busy rail index cannot break working
                    // Bristol bus directions. No repeated retry on this search.
                }
            }
            if(scheduledRail!=null && !busEnabled)
                return scheduledRail;
            if(!busEnabled)
                throw new Exception("No scheduled train journey was found within walking distance.");
            // Outside London, prefer the owner's private pre-indexed OpenRoad server. This keeps
            // the expensive regional GTFS parsing off the phone. If the private server is absent,
            // offline or still being configured, fall back transparently to the on-device planner.
            boolean serverPaired = OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
            if (serverPaired) {
                long providerStart = SystemClock.elapsedRealtime();
                try {
                    JSONObject response = OpenRoadServerClient.route(context, originLat, originLon, destLat, destLon, safeSettings,
                            BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                    Log.i(TIMING_TAG, "provider=private_server outcome=success ms=" + (SystemClock.elapsedRealtime()-providerStart));
                    return scheduledRail==null?response:mergeBusAndRail(response,scheduledRail);
                } catch (Exception serverFailure) {
                    if(scheduledRail!=null)return scheduledRail;
                    officialFailure = serverFailure;
                    Log.w(TIMING_TAG, "provider=private_server outcome=failed ms=" + (SystemClock.elapsedRealtime()-providerStart));
                }
            }
            if(scheduledRail!=null)return scheduledRail;
            // Never start a multi-megabyte timetable download in a foreground route search.
            // If the timetable isn't prepared, the background preload can populate it for a retry.
            if (!BodsJourneyPlanner.hasPreparedRegion(context,originLat,originLon,destLat,destLon)) {
                if (officialFailure == null) officialFailure = new Exception("Local bus timetables have not yet been prepared for this journey.");
                else officialFailure = new Exception(officialFailure.getMessage() + " No prepared local bus timetable is available for fallback.");
            } else try {
                long providerStart = SystemClock.elapsedRealtime();
                JSONObject result = BodsJourneyPlanner.plan(context, originLat, originLon, destLat, destLon, safeSettings);
                Log.i(TIMING_TAG, "provider=local_bods outcome=success ms=" + (SystemClock.elapsedRealtime()-providerStart));
                return result;
            } catch (Exception localFailure) {
                if (officialFailure == null) officialFailure = localFailure;
                else officialFailure = new Exception(officialFailure.getMessage() + " Local fallback: " + localFailure.getMessage());
            }
        }

        // TransportAPI is an explicit, optional fallback only. A free/limited TransportAPI plan
        // must never make the normal Directions button fail before the official-data path is tried.
        if (allowTransportApiFallback && has(transportId) && has(transportKey)) {
            return requestTransportApiJourney(originLat, originLon, destLat, destLon, transportId, transportKey, safeSettings);
        }

        String detail = officialFailure == null || officialFailure.getMessage() == null ? "Official public-transport data could not produce this journey." : officialFailure.getMessage();
        if (insideGreaterLondon(originLat, originLon) && insideGreaterLondon(destLat, destLon))
            throw new Exception(detail + " TransportAPI fallback is off; enable it in Public transport settings only if you want to use that paid/limited service.");
        throw new Exception(detail);
    }

    /** Keep at least one rail alternative alongside fast local bus journeys. */
    private static JSONObject mergeBusAndRail(JSONObject bus,JSONObject rail) throws Exception {
        java.util.List<JSONObject> all=new ArrayList<>();
        JSONArray b=bus.optJSONArray("routes"),r=rail.optJSONArray("routes");
        if(r!=null)for(int i=0;i<Math.min(2,r.length());i++){
            JSONObject item=r.optJSONObject(i);if(item!=null)all.add(item);
        }
        if(b!=null)for(int i=0;i<Math.min(2,b.length());i++){
            JSONObject item=b.optJSONObject(i);if(item!=null)all.add(item);
        }
        all.sort((x,y)->Long.compare(x.optJSONObject("summary")==null?Long.MAX_VALUE:
                x.optJSONObject("summary").optLong("travelTimeInSeconds",Long.MAX_VALUE),
                y.optJSONObject("summary")==null?Long.MAX_VALUE:
                y.optJSONObject("summary").optLong("travelTimeInSeconds",Long.MAX_VALUE)));
        JSONArray out=new JSONArray();
        for(int i=0;i<Math.min(3,all.size());i++)out.put(all.get(i));
        return new JSONObject(bus.toString()).put("routes",out)
                .put("clearRouteMultimodal",true);
    }

    private static JSONObject combineSegmentJourneys(List<JSONObject> segments, JSONArray viaStops) throws Exception {
        JSONArray combined = new JSONArray();
        int alternatives = 3;
        for (JSONObject segment : segments) {
            JSONArray routes = segment.optJSONArray("routes");
            if (routes == null || routes.length() == 0) throw new Exception("No public-transport journey was found for one of the added stops.");
            alternatives = Math.min(alternatives, Math.max(1, routes.length()));
        }
        for (int rank = 0; rank < alternatives; rank++) {
            JSONObject out = new JSONObject(); JSONArray legs = new JSONArray(), transitLegs = new JSONArray(), instructions = new JSONArray();
            long seconds = 0L, metres = 0L; String departure = "", arrival = ""; List<String> sources = new ArrayList<>();
            boolean anyLive = false, anyScheduled = false;
            for (int si = 0; si < segments.size(); si++) {
                JSONArray routes = segments.get(si).optJSONArray("routes"); JSONObject r = routes.optJSONObject(Math.min(rank, routes.length()-1)); if (r == null) continue;
                JSONObject summary = r.optJSONObject("summary"); if (summary != null) { seconds += summary.optLong("travelTimeInSeconds",0); metres += summary.optLong("lengthInMeters",0); }
                JSONArray rl = r.optJSONArray("legs"); if (rl != null) for (int i=0;i<rl.length();i++) legs.put(rl.opt(i));
                JSONArray tl = r.optJSONArray("transitLegs"); if (tl != null) for (int i=0;i<tl.length();i++) transitLegs.put(tl.opt(i));
                JSONArray ins = r.optJSONObject("guidance") == null ? null : r.optJSONObject("guidance").optJSONArray("instructions"); if (ins != null) for (int i=0;i<ins.length();i++) instructions.put(ins.opt(i));
                if (si == 0) departure = r.optString("clearRouteDeparture",""); if (si == segments.size()-1) arrival = r.optString("clearRouteArrival","");
                String status = r.optString("clearRouteDataStatus","scheduled"); if ("live".equals(status)||"mixed".equals(status)) anyLive=true; if (!"live".equals(status)) anyScheduled=true;
                if (has(r.optString("clearRouteDataSource",""))) addSource(sources, r.optString("clearRouteDataSource"));
            }
            String status = anyLive && anyScheduled ? "mixed" : anyLive ? "live" : "scheduled";
            out.put("summary",new JSONObject().put("travelTimeInSeconds",seconds).put("lengthInMeters",metres));
            out.put("legs",legs).put("transitLegs",transitLegs).put("guidance",new JSONObject().put("instructions",instructions));
            out.put("clearRouteTransit",true).put("clearRouteLabel",rank==0?"Recommended":"Public transport alternative");
            out.put("clearRouteDeparture",departure).put("clearRouteArrival",arrival).put("clearRouteDataStatus",status).put("clearRouteDataSource",joinSources(sources));
            out.put("clearRouteDataNote","Journey includes " + (viaStops == null ? 0 : viaStops.length()) + " added stop" + ((viaStops != null && viaStops.length()==1)?"":"s"));
            combined.put(out);
        }
        JSONObject response = new JSONObject().put("routes",combined);
        if (!segments.isEmpty()) {
            String region = segments.get(0).optString("clearRouteRegion", "");
            if (!region.isEmpty()) response.put("clearRouteRegion", region);
        }
        return response;
    }

    /** Lookup a bus number close to the current map/user location. TfL returns full route shape;
     * elsewhere BODS returns fresh official live vehicle positions for that line. */
    public static void lookupBusLine(Context context, double lat, double lon, String line,
                                     String tflKey, String bodsKey, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                String clean = line == null ? "" : line.trim();
                if (clean.toLowerCase(Locale.UK).startsWith("bus ")) clean = clean.substring(4).trim();
                if (clean.isEmpty()) throw new Exception("Enter a bus number or route name.");
                if (insideGreaterLondon(lat, lon)) {
                    callback.onSuccess(requestTflBusRoute(clean, lat, lon, tflKey));
                    return;
                }
                JSONObject scheduled = null;
                try {
                    if (OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL))
                        scheduled = OpenRoadServerClient.busService(context, clean, lat, lon, BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                } catch (Exception ignored) {}
                if (scheduled == null) scheduled = BodsGtfsCache.findBusRoute(context, lat, lon, clean);
                if (scheduled != null) {
                    cacheNaptanStopsAsync(context, scheduled.optJSONArray("stops"));
                    // On-demand live vehicle data is now provided exclusively by the paired server.
                    scheduled.put("liveAvailable", OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL));
                    scheduled.put("vehicles", new JSONArray());
                    callback.onSuccess(scheduled.toString());
                    return;
                }
                throw new Exception("No official route data was found for bus " + clean + ".");
            } catch (Exception e) {
                callback.onError(e.getMessage() == null ? "Bus route lookup failed" : e.getMessage());
            }
        });
    }

    public static void lookupBusStop(Context context, String stopId, double lat, double lon, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                if (!OpenRoadServerClient.configured(context, BuildConfig.BUNDLED_OPENROAD_SERVER_URL)) throw new Exception("The private OpenRoad transport server is needed for bus-stop departures.");
                callback.onSuccess(OpenRoadServerClient.busStop(context, stopId, lat, lon, BuildConfig.BUNDLED_OPENROAD_SERVER_URL).toString());
            } catch (Exception e) { callback.onError(e.getMessage() == null ? "Bus-stop information unavailable" : e.getMessage()); }
        });
    }

    public static void lookupBusLive(Context context, double lat, double lon, String line, Callback callback) {
        EXECUTOR.execute(() -> {
            try {
                String clean=line==null?"":line.trim();
                if(clean.toLowerCase(Locale.UK).startsWith("bus "))clean=clean.substring(4).trim();
                if(clean.isEmpty())throw new Exception("No bus number is selected.");
                String xml=OpenRoadServerClient.bodsLiveXml(context,clean,lat,lon,BuildConfig.BUNDLED_OPENROAD_SERVER_URL);
                callback.onSuccess(parseBodsBusVehicles(xml,clean));
            } catch(Exception e){callback.onError(e.getMessage()==null?"Live buses unavailable":e.getMessage());}
        });
    }

    public static JSONObject cacheStatus(Context context) {
        JSONObject out = new JSONObject();
        try {
            File dir = new File(context.getCacheDir(), "transit/naptan");
            File[] files = dir.listFiles((d, name) -> name.endsWith(".csv"));
            int count = files == null ? 0 : files.length;
            long newest = 0L;
            if (files != null) for (File f : files) newest = Math.max(newest, f.lastModified());
            out.put("areas", count);
            out.put("lastUpdated", newest);
            out.put("bodsGtfs", BodsGtfsCache.status(context));
        } catch (Exception ignored) {}
        return out;
    }

    // -----------------------------------------------------------------------------------------
    // TfL — official direct London journey planning
    // -----------------------------------------------------------------------------------------

    private static String requestTflJourney(double originLat, double originLon,
                                            double destLat, double destLon, String key, JSONObject settings) throws Exception {
        String from = String.format(Locale.US, "%.6f,%.6f", originLat, originLon);
        String to = String.format(Locale.US, "%.6f,%.6f", destLat, destLon);
        StringBuilder query = new StringBuilder("?useRealTimeLiveArrivals=true");
        String ranking = settings == null ? "balanced" : settings.optString("ranking", "balanced");
        query.append("&journeyPreference=").append("changes".equals(ranking) ? "LeastInterchange" : "LeastTime");
        String tflModes = tflModes(settings); if (!tflModes.isEmpty()) query.append("&mode=").append(Uri.encode(tflModes));
        if (settings != null) {
            int maxWalk = settings.optInt("maxWalk", 999); if (maxWalk > 0 && maxWalk < 999) query.append("&maxWalkingMinutes=").append(maxWalk);
            String speed = settings.optString("walkSpeed", "normal"); query.append("&walkingSpeed=").append("slow".equals(speed) ? "Slow" : "fast".equals(speed) ? "Fast" : "Average");
            String access = settings.optString("accessibility", "none");
            if ("avoid-stairs".equals(access)) query.append("&accessibilityPreference=NoSolidStairs");
            else if ("platform".equals(access)) query.append("&accessibilityPreference=StepFreeToPlatform");
            else if ("full".equals(access)) query.append("&accessibilityPreference=StepFreeToVehicle");
        }
        String url = "https://api.tfl.gov.uk/Journey/JourneyResults/" + Uri.encode(from) + "/to/" + Uri.encode(to)
                + query + tflKeyQuery(key);
        JSONObject raw = new JSONObject(get(url, null));
        JSONArray journeys = raw.optJSONArray("journeys");
        if (journeys == null || journeys.length() == 0) throw new Exception("TfL did not find a public-transport journey.");

        int resultLimit = 3;
        JSONArray routes = new JSONArray();
        for (int ji = 0; ji < Math.min(resultLimit, journeys.length()); ji++) {
            JSONObject journey = journeys.optJSONObject(ji);
            if (journey == null) continue;
            JSONObject out = new JSONObject();
            JSONArray routeLegs = new JSONArray();
            JSONArray transitLegs = new JSONArray();
            JSONArray instructions = new JSONArray();
            JSONArray legs = journey.optJSONArray("legs");
            double totalDistance = 0.0;
            double routeOffset = 0.0;
            int globalPointIndex = 0;
            if (legs != null) {
                for (int li = 0; li < legs.length(); li++) {
                    JSONObject leg = legs.optJSONObject(li); if (leg == null) continue;
                    JSONObject path = leg.optJSONObject("path");
                    JSONArray points = parseTflLineString(path == null ? "" : path.optString("lineString", ""));
                    double legDistance = pointsDistance(points);
                    if (points.length() > 0) routeLegs.put(new JSONObject().put("points", points));
                    totalDistance += legDistance;

                    JSONObject modeObj = leg.optJSONObject("mode");
                    String mode = normalizeMode(modeObj == null ? "" : modeObj.optString("id", modeObj.optString("name", "")));
                    String line = tflLineName(leg);
                    JSONObject dep = leg.optJSONObject("departurePoint");
                    JSONObject arr = leg.optJSONObject("arrivalPoint");
                    String fromName = dep == null ? "" : dep.optString("commonName", "");
                    String toName = arr == null ? "" : arr.optString("commonName", "");
                    String departure = clock(leg.optString("departureTime", ""));
                    String arrival = clock(leg.optString("arrivalTime", ""));
                    JSONObject instruction = leg.optJSONObject("instruction");
                    String message = instruction == null ? "" : instruction.optString("summary", "");
                    if (message.isEmpty()) message = legMessage(mode, line, "", toName);

                    int stopCount = path != null && path.optJSONArray("stopPoints") != null ? path.optJSONArray("stopPoints").length() : 0;
                    JSONObject tl = new JSONObject()
                            .put("mode", mode).put("line", line).put("from", fromName).put("to", toName).put("stopCount", stopCount)
                            .put("departure", departure).put("arrival", arrival).put("durationSeconds", Math.max(0, leg.optInt("duration", 0)) * 60L)
                            .put("timeStatus", "live").put("dataSource", "TfL")
                            .put("fromStopId", dep == null ? "" : dep.optString("naptanId", ""))
                            .put("toStopId", arr == null ? "" : arr.optString("naptanId", ""))
                            .put("fromLat", dep == null ? Double.NaN : dep.optDouble("lat", Double.NaN))
                            .put("fromLon", dep == null ? Double.NaN : dep.optDouble("lon", Double.NaN))
                            .put("toLat", arr == null ? Double.NaN : arr.optDouble("lat", Double.NaN))
                            .put("toLon", arr == null ? Double.NaN : arr.optDouble("lon", Double.NaN))
                            .put("geometryStatus", points.length() >= 2 ? "exact" : "fallback");
                    transitLegs.put(tl);

                    instructions.put(new JSONObject()
                            .put("pointIndex", globalPointIndex)
                            .put("routeOffsetInMeters", routeOffset)
                            .put("travelTimeInSeconds", Math.max(0, leg.optInt("duration", 0)) * 60L)
                            .put("message", message)
                            .put("maneuver", "STRAIGHT")
                            .put("instructionType", "TRANSIT"));
                    routeOffset += legDistance;
                    globalPointIndex += points.length();
                }
            }
            JSONObject summary = new JSONObject()
                    .put("travelTimeInSeconds", Math.max(0, journey.optInt("duration", 0)) * 60L)
                    .put("lengthInMeters", Math.round(totalDistance));
            out.put("summary", summary);
            out.put("legs", routeLegs);
            out.put("guidance", new JSONObject().put("instructions", instructions));
            out.put("transitLegs", transitLegs);
            out.put("clearRouteLabel", ji == 0 ? "Recommended" : "Public transport alternative");
            out.put("clearRouteTransit", true);
            out.put("clearRouteDeparture", clock(journey.optString("startDateTime", "")));
            out.put("clearRouteArrival", clock(journey.optString("arrivalDateTime", "")));
            out.put("clearRouteDataStatus", "live");
            out.put("clearRouteLiveStatus", "complete");
            out.put("clearRouteDataSource", "TfL");
            out.put("clearRouteDataNote", "Official TfL journey planner · live arrivals enabled");
            routes.put(out);
        }
        return new JSONObject().put("routes", routes).put("clearRouteHasMore", journeys.length() > resultLimit).put("clearRouteResultLimit", resultLimit).toString();
    }

    private static JSONArray parseTflLineString(String encoded) {
        JSONArray points = new JSONArray();
        try {
            JSONArray pairs = new JSONArray(encoded);
            for (int i = 0; i < pairs.length(); i++) {
                JSONArray pair = pairs.optJSONArray(i); if (pair == null || pair.length() < 2) continue;
                // TfL Journey Planner lineString is [latitude, longitude].
                points.put(new JSONObject().put("latitude", pair.optDouble(0)).put("longitude", pair.optDouble(1)));
            }
        } catch (Exception ignored) {}
        return points;
    }

    private static String tflLineName(JSONObject leg) {
        JSONArray options = leg.optJSONArray("routeOptions");
        if (options != null && options.length() > 0) {
            JSONObject o = options.optJSONObject(0);
            if (o != null) {
                String n = o.optString("name", "");
                if (!n.isEmpty()) return n;
                JSONObject li = o.optJSONObject("lineIdentifier");
                if (li != null) return li.optString("name", li.optString("id", ""));
            }
        }
        return "";
    }

    private static String requestTflBusRoute(String line, double queryLat, double queryLon, String key) throws Exception {
        JSONObject out = new JSONObject().put("line", line).put("source", "TfL").put("coverage", "route");
        JSONArray geometries = new JSONArray();
        JSONArray stops = new JSONArray();
        for (String direction : new String[]{"outbound", "inbound"}) {
            String url = "https://api.tfl.gov.uk/Line/" + Uri.encode(line) + "/Route/Sequence/" + direction
                    + "?serviceTypes=Regular" + tflKeyQuery(key);
            try {
                JSONObject raw = new JSONObject(get(url, null));
                JSONArray strings = raw.optJSONArray("lineStrings");
                if (strings != null) for (int i = 0; i < strings.length(); i++) {
                    Object rawString = strings.opt(i);
                    JSONArray multi = rawString instanceof String ? new JSONArray((String)rawString) : (rawString instanceof JSONArray ? (JSONArray)rawString : null);
                    if (multi == null) continue;
                    for (int mi = 0; mi < multi.length(); mi++) {
                        JSONArray coords = multi.optJSONArray(mi); if (coords == null) continue;
                        JSONArray converted = new JSONArray();
                        for (int ci = 0; ci < coords.length(); ci++) {
                            JSONArray c = coords.optJSONArray(ci); if (c == null || c.length() < 2) continue;
                            // Route Sequence geometry is GeoJSON order [lon, lat].
                            converted.put(new JSONArray().put(c.optDouble(0)).put(c.optDouble(1)));
                        }
                        if (converted.length() > 1) geometries.put(new JSONObject().put("direction", direction).put("coordinates", converted));
                    }
                }
                JSONArray stations = raw.optJSONArray("stations");
                if (stations != null) for (int i = 0; i < stations.length(); i++) {
                    JSONObject s = stations.optJSONObject(i); if (s == null) continue;
                    JSONObject stop = new JSONObject().put("id", s.optString("id", s.optString("naptanId", "")))
                            .put("name", s.optString("name", s.optString("commonName", "Stop")))
                            .put("direction", direction);
                    double stopLat = s.optDouble("lat", Double.NaN), stopLon = s.optDouble("lon", Double.NaN);
                    if (Double.isFinite(stopLat) && Double.isFinite(stopLon)) stop.put("lat", stopLat).put("lon", stopLon);
                    stops.put(stop);
                }
            } catch (Exception ignored) {}
        }
        if (geometries.length() == 0) throw new Exception("TfL did not return route geometry for bus " + line + ".");
        out.put("geometries", geometries).put("stops", stops);
        JSONObject nearest = null; double nearestDistance = Double.POSITIVE_INFINITY;
        for (int i = 0; i < stops.length(); i++) { JSONObject stop = stops.optJSONObject(i); if (stop == null) continue; double lat=stop.optDouble("lat",Double.NaN),lon=stop.optDouble("lon",Double.NaN); if(!Double.isFinite(lat)||!Double.isFinite(lon))continue; double d=distanceMetres(queryLat,queryLon,lat,lon); if(d<nearestDistance){nearestDistance=d;nearest=stop;} }
        if (nearest != null && has(nearest.optString("id", ""))) {
            try {
                String arrivalsUrl = "https://api.tfl.gov.uk/StopPoint/" + Uri.encode(nearest.optString("id")) + "/Arrivals" + (has(key)?"?app_key="+Uri.encode(key.trim()):"");
                JSONArray arrivals = new JSONArray(get(arrivalsUrl, null)); List<JSONObject> matches = new ArrayList<>();
                for (int i=0;i<arrivals.length();i++){JSONObject a=arrivals.optJSONObject(i);if(a==null)continue;String lineId=a.optString("lineId",a.optString("lineName",""));if(line.equalsIgnoreCase(lineId)||line.equalsIgnoreCase(a.optString("lineName","")))matches.add(a);}
                matches.sort((a,b)->Integer.compare(a.optInt("timeToStation",Integer.MAX_VALUE),b.optInt("timeToStation",Integer.MAX_VALUE)));
                JSONArray deps = new JSONArray(); for(JSONObject a:matches){deps.put(new JSONObject().put("time",clock(a.optString("expectedArrival",""))).put("destination",a.optString("destinationName","")).put("direction","Live TfL arrival"));if(deps.length()>=12)break;}
                out.put("timetable",new JSONObject().put("stopId",nearest.optString("id")).put("stopName",nearest.optString("name","Nearby stop")).put("departures",deps).put("source","TfL live arrivals"));
                if(deps.length()>0)out.put("coverage","route+live-arrivals");
            } catch(Exception ignored) {}
        }
        return out.toString();
    }

    // -----------------------------------------------------------------------------------------
    // TransportAPI — paid/freemium multimodal fallback, enriched with official live feeds
    // -----------------------------------------------------------------------------------------

    private static JSONObject requestTransportApiJourney(double originLat, double originLon,
                                                          double destLat, double destLon,
                                                          String appId, String appKey, JSONObject settings) throws Exception {
        String from = "lonlat:" + originLon + "," + originLat;
        String to = "lonlat:" + destLon + "," + destLat;
        // TransportAPI's current Journey Planner example explicitly selects the SilverRail
        // engine. Earlier OpenRoad builds also sent a comma-separated multi-mode filter here;
        // that can produce HTTP 400 responses on the current endpoint. Request a normal
        // multimodal plan and enforce the user's mode choices locally when results are ranked.
        String url = "https://transportapi.com/v3/uk/public/journey/from/" + Uri.encode(from)
                + "/to/" + Uri.encode(to) + ".json?service=silverrail&app_id=" + Uri.encode(appId.trim())
                + "&app_key=" + Uri.encode(appKey.trim());
        if (settings != null && transportApiModes(settings).isEmpty() && hasExplicitModeSelection(settings))
            throw new Exception("None of the selected transport types is supported by the GB-wide journey planner in this area.");
        JSONObject source;
        try {
            source = new JSONObject(get(url, null));
        } catch (Exception e) {
            String message = e.getMessage() == null ? "" : e.getMessage();
            if (message.toLowerCase(Locale.UK).contains("not part of your plan")) {
                throw new Exception("TransportAPI accepted the configured app credentials, but your current plan does not include the TAPI Journey Planner endpoint.");
            }
            throw e;
        }
        JSONArray sourceRoutes = source.optJSONArray("routes");
        if (sourceRoutes == null || sourceRoutes.length() == 0) throw new Exception("No public-transport journeys were found.");
        JSONArray routes = new JSONArray();
        int resultLimit = 3;
        for (int ri = 0; ri < Math.min(resultLimit, sourceRoutes.length()); ri++) {
            JSONObject srcRoute = sourceRoutes.optJSONObject(ri); if (srcRoute == null) continue;
            JSONObject outRoute = new JSONObject();
            JSONObject summary = new JSONObject().put("travelTimeInSeconds", parseDurationSeconds(srcRoute.optString("duration", "")));
            JSONArray parts = srcRoute.optJSONArray("route_parts");
            JSONArray legs = new JSONArray();
            JSONArray instructions = new JSONArray();
            JSONArray transitLegs = new JSONArray();
            double totalDistance = 0.0, routeOffset = 0.0;
            int globalPointIndex = 0;
            if (parts != null) {
                for (int pi = 0; pi < parts.length(); pi++) {
                    JSONObject part = parts.optJSONObject(pi); if (part == null) continue;
                    JSONArray coords = part.optJSONArray("coordinates");
                    JSONArray points = new JSONArray();
                    double partDistance = 0.0;
                    double prevLat = Double.NaN, prevLon = Double.NaN;
                    if (coords != null) for (int ci = 0; ci < coords.length(); ci++) {
                        JSONArray c = coords.optJSONArray(ci); if (c == null || c.length() < 2) continue;
                        double lon = c.optDouble(0), lat = c.optDouble(1);
                        points.put(new JSONObject().put("latitude", lat).put("longitude", lon));
                        if (Double.isFinite(prevLat)) partDistance += distanceMetres(prevLat, prevLon, lat, lon);
                        prevLat = lat; prevLon = lon;
                    }
                    if (points.length() > 0) legs.put(new JSONObject().put("points", points));
                    String mode = normalizeMode(part.optString("mode", ""));
                    String line = part.optString("line_name", "");
                    String fromName = part.optString("from_point_name", "");
                    String toName = part.optString("to_point_name", "");
                    String destination = part.optString("destination", "");
                    JSONObject fromPlace = nestedPlace(part.optJSONObject("from_point"));
                    JSONObject toPlace = nestedPlace(part.optJSONObject("to_point"));
                    String fromAtco = fromPlace.optString("atcocode", "");
                    String toAtco = toPlace.optString("atcocode", "");
                    String fromCrs = fromPlace.optString("station_code", fromPlace.optString("crs", ""));
                    String toCrs = toPlace.optString("station_code", toPlace.optString("crs", ""));
                    JSONObject tl = new JSONObject()
                            .put("mode", mode).put("line", line).put("from", fromName).put("to", toName).put("destination", destination)
                            .put("stopCount", part.optJSONArray("stops") == null ? 0 : part.optJSONArray("stops").length())
                            .put("departure", part.optString("departure_time", "")).put("arrival", part.optString("arrival_time", ""))
                            .put("duration", part.optString("duration", "")).put("durationSeconds", parseDurationSeconds(part.optString("duration", ""))).put("timeStatus", "scheduled")
                            .put("dataSource", "TransportAPI schedule").put("fromAtco", fromAtco).put("toAtco", toAtco)
                            .put("fromCrs", fromCrs).put("toCrs", toCrs);
                    if (points.length() > 0) {
                        JSONObject p = points.optJSONObject(0);
                        if (p != null) tl.put("fromLat", p.optDouble("latitude")).put("fromLon", p.optDouble("longitude"));
                    }
                    transitLegs.put(tl);
                    instructions.put(new JSONObject().put("pointIndex", globalPointIndex).put("routeOffsetInMeters", routeOffset)
                            .put("travelTimeInSeconds", 0).put("message", legMessage(mode, line, destination, toName))
                            .put("maneuver", "STRAIGHT").put("instructionType", "TRANSIT"));
                    routeOffset += partDistance; totalDistance += partDistance; globalPointIndex += points.length();
                }
            }
            summary.put("lengthInMeters", Math.round(totalDistance));
            outRoute.put("summary", summary).put("legs", legs)
                    .put("guidance", new JSONObject().put("instructions", instructions)).put("transitLegs", transitLegs)
                    .put("clearRouteLabel", ri == 0 ? "Recommended" : "Public transport alternative")
                    .put("clearRouteTransit", true)
                    .put("clearRouteDeparture", srcRoute.optString("departure_time", ""))
                    .put("clearRouteArrival", srcRoute.optString("arrival_time", ""))
                    .put("clearRouteDataStatus", "scheduled")
                    .put("clearRouteDataSource", "TransportAPI")
                    .put("clearRouteDataNote", "Scheduled journey plan · official live feeds checked where configured");
            routes.put(outRoute);
        }
        return new JSONObject().put("routes", routes).put("clearRouteHasMore", sourceRoutes.length() > resultLimit).put("clearRouteResultLimit", resultLimit);
    }

    /**
     * Replace straight-line public-transport walking legs with real pedestrian geometry from
     * OpenRoad's existing OSM/Valhalla walking router. This is path enrichment only: the public
     * transport timetable remains authoritative for departure/arrival feasibility.
     */
    private static boolean enrichWalkingGeometry(Context context, JSONObject response, int fromRoute, int toRouteExclusive) {
        try {
            JSONArray routes = response == null ? null : response.optJSONArray("routes");
            if (routes == null) return false;
            boolean changed = false;
            int end = Math.min(routes.length(), Math.max(fromRoute, toRouteExclusive));
            for (int ri = Math.max(0, fromRoute); ri < end; ri++) {
                JSONObject route = routes.optJSONObject(ri); if (route == null) continue;
                boolean routeChanged = false;
                JSONArray transitLegs = route.optJSONArray("transitLegs");
                JSONArray mapLegs = route.optJSONArray("legs");
                if (transitLegs == null || mapLegs == null) continue;
                for (int li = 0; li < transitLegs.length(); li++) {
                    JSONObject leg = transitLegs.optJSONObject(li);
                    if (leg == null || !"foot".equals(normalizeMode(leg.optString("mode", "")))) continue;
                    if ("exact".equals(leg.optString("geometryStatus", ""))) continue;
                    double aLat = leg.optDouble("fromLat", Double.NaN), aLon = leg.optDouble("fromLon", Double.NaN);
                    double bLat = leg.optDouble("toLat", Double.NaN), bLon = leg.optDouble("toLon", Double.NaN);
                    if (!Double.isFinite(aLat) || !Double.isFinite(aLon) || !Double.isFinite(bLat) || !Double.isFinite(bLon)) continue;
                    if (distanceMetres(aLat, aLon, bLat, bLon) < 25) continue;
                    try {
                        JSONObject walking = new JSONObject(ApiClient.routeSync(context, aLat, aLon, bLat, bLon, "walk"));
                        JSONArray walkRoutes = walking.optJSONArray("routes");
                        JSONObject walkRoute = walkRoutes == null ? null : walkRoutes.optJSONObject(0);
                        JSONArray routedPoints = flattenRoutePoints(walkRoute);
                        if (routedPoints.length() < 2) continue;
                        int mapIndex = findMapLegForEndpoints(mapLegs, aLat, aLon, bLat, bLon);
                        if (mapIndex < 0) continue;
                        JSONObject mapLeg = mapLegs.optJSONObject(mapIndex); if (mapLeg == null) continue;
                        mapLeg.put("points", routedPoints);
                        JSONObject summary = walkRoute.optJSONObject("summary");
                        if (summary != null) {
                            long metres = Math.round(summary.optDouble("lengthInMeters", leg.optDouble("distanceMetres", 0)));
                            long seconds = Math.round(summary.optDouble("travelTimeInSeconds", leg.optDouble("durationSeconds", 0)));
                            if (metres > 0) leg.put("distanceMetres", metres);
                            if (seconds > 0) leg.put("durationSeconds", seconds);
                        }
                        leg.put("geometrySource", "OpenStreetMap pedestrian routing").put("geometryStatus", "exact");
                        changed = true; routeChanged = true;
                    } catch (Exception ignored) {
                        if ("loading".equals(leg.optString("geometryStatus", ""))) { leg.put("geometryStatus", "fallback"); changed = true; routeChanged = true; }
                    }
                }
                if (routeChanged) reconcileWalkingTiming(route);
            }
            return changed;
        } catch (Exception ignored) { return false; }
    }

    /** Re-evaluate access/egress walking after real pedestrian routing. This prevents a straight-line
     * estimate from keeping a journey that the user can no longer physically reach in time. */
    private static void reconcileWalkingTiming(JSONObject route) {
        try {
            JSONArray legs = route.optJSONArray("transitLegs"); if (legs == null || legs.length() == 0) return;
            int firstTransit = -1, lastTransit = -1;
            for (int i = 0; i < legs.length(); i++) {
                JSONObject leg = legs.optJSONObject(i); if (leg == null) continue;
                if (!"foot".equals(normalizeMode(leg.optString("mode", "")))) { if (firstTransit < 0) firstTransit = i; lastTransit = i; }
            }
            if (firstTransit < 0) return;
            long access = 0, egress = 0;
            for (int i=0;i<firstTransit;i++){JSONObject l=legs.optJSONObject(i);if(l!=null&&"foot".equals(normalizeMode(l.optString("mode",""))))access+=Math.max(0,l.optLong("durationSeconds",0));}
            for (int i=lastTransit+1;i<legs.length();i++){JSONObject l=legs.optJSONObject(i);if(l!=null&&"foot".equals(normalizeMode(l.optString("mode",""))))egress+=Math.max(0,l.optLong("durationSeconds",0));}
            JSONObject first = legs.optJSONObject(firstTransit), last = legs.optJSONObject(lastTransit); if (first == null || last == null) return;
            int depClock = clockSeconds(first.optString("departure", "")), arrClock = clockSeconds(last.optString("arrival", "")); if (depClock < 0 || arrClock < 0) return;
            int now = LocalTime.now(ZoneId.of("Europe/London")).toSecondOfDay();
            long dep = depClock; while (dep < now - 6 * 3600L) dep += 86400L;
            long arr = arrClock; while (arr < dep) arr += 86400L;
            boolean feasible = now + access <= dep + 30L;
            long leave = Math.max(now, dep - access), finish = arr + egress;
            route.put("clearRouteFeasible", feasible);
            route.put("clearRouteDeparture", displayClockLong(leave));
            route.put("clearRouteArrival", displayClockLong(finish));
            JSONObject summary = route.optJSONObject("summary"); if (summary != null) summary.put("travelTimeInSeconds", Math.max(60L, finish - leave));
            if (!feasible) route.put("clearRouteWarning", "Walking route to the first stop is longer than the timetable estimate; this departure is no longer reachable.");
        } catch (Exception ignored) {}
    }

    private static int clockSeconds(String value) {
        try { String[] p=value.trim().split(":"); if(p.length<2)return -1; return Integer.parseInt(p[0])*3600+Integer.parseInt(p[1])*60+(p.length>2?Integer.parseInt(p[2]):0); }
        catch(Exception e){ return -1; }
    }
    private static String displayClockLong(long sec) { long s=((sec%86400L)+86400L)%86400L; return String.format(Locale.UK,"%02d:%02d",s/3600L,(s%3600L)/60L); }

    private static JSONArray flattenRoutePoints(JSONObject route) {
        JSONArray out = new JSONArray(); if (route == null) return out;
        JSONArray legs = route.optJSONArray("legs"); if (legs == null) return out;
        for (int li = 0; li < legs.length(); li++) {
            JSONObject leg = legs.optJSONObject(li); JSONArray points = leg == null ? null : leg.optJSONArray("points");
            if (points == null) continue;
            for (int pi = 0; pi < points.length(); pi++) {
                JSONObject p = points.optJSONObject(pi); if (p == null) continue;
                if (out.length() > 0 && pi == 0) {
                    JSONObject prev = out.optJSONObject(out.length()-1);
                    if (prev != null && Math.abs(prev.optDouble("latitude") - p.optDouble("latitude")) < 1e-7
                            && Math.abs(prev.optDouble("longitude") - p.optDouble("longitude")) < 1e-7) continue;
                }
                out.put(p);
            }
        }
        return out;
    }

    private static int findMapLegForEndpoints(JSONArray mapLegs, double aLat, double aLon, double bLat, double bLon) {
        int best = -1; double bestScore = Double.POSITIVE_INFINITY;
        for (int i = 0; i < mapLegs.length(); i++) {
            JSONObject leg = mapLegs.optJSONObject(i); JSONArray pts = leg == null ? null : leg.optJSONArray("points");
            if (pts == null || pts.length() < 2) continue;
            JSONObject first = pts.optJSONObject(0), last = pts.optJSONObject(pts.length()-1);
            if (first == null || last == null) continue;
            double fLat = first.optDouble("latitude", Double.NaN), fLon = first.optDouble("longitude", Double.NaN);
            double lLat = last.optDouble("latitude", Double.NaN), lLon = last.optDouble("longitude", Double.NaN);
            if (!Double.isFinite(fLat) || !Double.isFinite(fLon) || !Double.isFinite(lLat) || !Double.isFinite(lLon)) continue;
            double score = distanceMetres(aLat, aLon, fLat, fLon) + distanceMetres(bLat, bLon, lLat, lLon);
            double reverse = distanceMetres(aLat, aLon, lLat, lLon) + distanceMetres(bLat, bLon, fLat, fLon);
            score = Math.min(score, reverse);
            if (score < bestScore) { bestScore = score; best = i; }
        }
        return bestScore <= 300.0 ? best : -1;
    }

    private static void enrichOfficialLive(Context context, JSONObject response, String bodsKey,
                                           String darwinUser, String darwinPassword) throws Exception {
        JSONArray routes = response.optJSONArray("routes"); if (routes == null) return;
        for (int ri = 0; ri < routes.length(); ri++) {
            JSONObject route = routes.optJSONObject(ri); if (route == null) continue;
            JSONArray legs = route.optJSONArray("transitLegs"); if (legs == null) continue;
            boolean anyOfficialLive = false;
            List<String> sources = new ArrayList<>();
            if (has(route.optString("clearRouteDataSource", ""))) addSource(sources, route.optString("clearRouteDataSource"));
            for (int li = 0; li < legs.length(); li++) {
                JSONObject leg = legs.optJSONObject(li); if (leg == null) continue;
                String fromAtco = leg.optString("fromAtco", "");
                String toAtco = leg.optString("toAtco", "");
                cacheNaptanAreaAsync(context, fromAtco);
                cacheNaptanAreaAsync(context, toAtco);
                String mode = leg.optString("mode", "");
                // No automatic live-vehicle requests: protects shared JustHostMe hosting.
                // Only explicit 'Live buses' button presses call the BODS gateway.
                // Rail Data is now accessed only through the paired OpenRoad server.
                // Live train-leg enrichment will be reinstated via the server in a later phase.
            }
            if (anyOfficialLive) {
                route.put("clearRouteDataStatus", "mixed");
                route.put("clearRouteDataSource", joinSources(sources));
                route.put("clearRouteDataNote", "Scheduled journey plan enriched with fresh official live data");
                route.put("clearRouteLiveStatus", "complete");
            } else route.put("clearRouteLiveStatus", "unavailable");
            // Promote route-level time only when the first/last actual leg has a real live prediction.
            for (int li = 0; li < legs.length(); li++) {
                JSONObject leg = legs.optJSONObject(li);
                if (leg != null && "live".equals(leg.optString("timeStatus")) && has(leg.optString("liveDeparture"))) {
                    route.put("clearRouteDeparture", leg.optString("liveDeparture"));
                    break;
                }
            }
        }
    }

    // -----------------------------------------------------------------------------------------
    // BODS — official England bus live vehicle positions
    // -----------------------------------------------------------------------------------------

    private static String parseBodsBusVehicles(String xml, String line) throws Exception {
        XmlPullParser parser = XmlPullParserFactory.newInstance().newPullParser();
        parser.setInput(new StringReader(xml));
        JSONArray vehicles = new JSONArray();
        String tag = "", recorded = "", lineRef = "", published = "", destination = "", vehicleRef = "";
        double vLat = Double.NaN, vLon = Double.NaN, bearing = Double.NaN;
        boolean matchedService = false, hasFresh = false;
        int event = parser.getEventType();
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG) tag = parser.getName();
            else if (event == XmlPullParser.TEXT) {
                String text = parser.getText() == null ? "" : parser.getText().trim();
                if (!text.isEmpty()) {
                    if ("RecordedAtTime".equals(tag)) recorded = text;
                    else if ("LineRef".equals(tag)) lineRef = text;
                    else if ("PublishedLineName".equals(tag)) published = text;
                    else if ("DestinationName".equals(tag)) destination = text;
                    else if ("VehicleRef".equals(tag)) vehicleRef = text;
                    else if ("Latitude".equals(tag)) try { vLat = Double.parseDouble(text); } catch (Exception ignored) {}
                    else if ("Longitude".equals(tag)) try { vLon = Double.parseDouble(text); } catch (Exception ignored) {}
                    else if ("Bearing".equals(tag)) try { bearing = Double.parseDouble(text); } catch (Exception ignored) {}
                }
            } else if (event == XmlPullParser.END_TAG && "VehicleActivity".equals(parser.getName())) {
                if ((line.equalsIgnoreCase(lineRef) || line.equalsIgnoreCase(published)) && Double.isFinite(vLat) && Double.isFinite(vLon)) {
                    matchedService = true;
                    long age = ageMs(recorded);
                    if (age >= 0 && age <= BODS_LAST_KNOWN_MS) {
                        boolean fresh = age <= BODS_FRESH_MS;
                        hasFresh |= fresh;
                        vehicles.put(new JSONObject().put("lat", vLat).put("lon", vLon)
                            .put("recordedAt", recorded).put("destination", destination)
                            .put("vehicleRef", vehicleRef).put("bearing", bearing)
                            .put("lastKnown", !fresh).put("ageMinutes", Math.round(age / 60000.0)));
                    }
                }
                recorded=lineRef=published=destination=vehicleRef=""; vLat=vLon=bearing=Double.NaN;
            }
            event = parser.next();
        }
        if (vehicles.length() == 0) {
            if (matchedService) throw new Exception("Only older BODS positions exist for this service here; no recent vehicle is available.");
            throw new Exception("No tracked bus " + line + " was reported in this map area. Try another section of its route.");
        }
        return new JSONObject().put("line", line).put("source", "BODS")
            .put("coverage", hasFresh ? "live-vehicles" : "last-known-vehicles")
            .put("vehicles", vehicles)
            .put("message", hasFresh ? "Fresh official bus positions; older markers are dimmed."
                : "Last-known positions only (up to 15 minutes old). These are not live locations.")
            .toString();
    }

    // -----------------------------------------------------------------------------------------
    // National Rail Darwin — official real-time train departures
    // -----------------------------------------------------------------------------------------

    private static boolean enrichDarwin(JSONObject leg, String apiKey, String ignoredLegacyPassword) throws Exception {
        String from = leg.optString("fromCrs", "").trim().toUpperCase(Locale.UK);
        String to = leg.optString("toCrs", "").trim().toUpperCase(Locale.UK);
        if (from.length() != 3 || !has(apiKey)) return false;
        String url = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/" + Uri.encode(from)
                + "?numRows=20" + (to.length()==3 ? "&filterCrs=" + Uri.encode(to) + "&filterType=to" : "")
                + "&timeOffset=0&timeWindow=120";
        Map<String,String> headers = new HashMap<>();
        headers.put("x-apikey", apiKey.trim());
        JSONObject raw = new JSONObject(get(url, headers));
        JSONArray services = raw.optJSONArray("trainServices");
        if (services == null || services.length() == 0) return false;
        String scheduled = leg.optString("departure", "");
        JSONObject best = null;
        for (int i = 0; i < services.length(); i++) {
            JSONObject candidate = services.optJSONObject(i); if (candidate == null) continue;
            if (scheduled.equals(candidate.optString("std", ""))) { best = candidate; break; }
            if (best == null) best = candidate;
        }
        if (best == null) return false;
        String std = best.optString("std", scheduled);
        String etd = best.optString("etd", "");
        boolean cancelled = best.optBoolean("isCancelled", false) || "cancelled".equalsIgnoreCase(etd);
        String live = cancelled ? "Cancelled" : ("on time".equalsIgnoreCase(etd) ? std : etd);
        leg.put("dataSource", "National Rail Darwin · RDM").put("timeStatus", "live").put("liveDeparture", live)
                .put("platform", best.optString("platform", "")).put("cancelled", cancelled);
        if (has(best.optString("delayReason", ""))) leg.put("liveNote", best.optString("delayReason"));
        if (has(best.optString("cancelReason", ""))) leg.put("liveNote", best.optString("cancelReason"));
        return true;
    }

    // Phase 2 foundation: read-only Rail Data Marketplace departure board.
    // Access stays on the user's device; the RDM consumer key is retrieved from
    // Android Keystore, sent only in x-apikey over TLS, and never written to logs.
    // This is live service information, NOT a national journey-planning engine.
    public static JSONObject railDepartureBoard(String apiKey, String crs) throws Exception {
        if (!has(apiKey)) throw new Exception("Rail Data Marketplace key is not configured.");
        String station = crs == null ? "" : crs.trim().toUpperCase(Locale.UK);
        if (!station.matches("[A-Z]{3}"))
            throw new Exception("Enter a three-letter National Rail station code, such as BRI.");
        String url = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
                + Uri.encode(station) + "?numRows=8&timeOffset=0&timeWindow=120";
        Map<String,String> headers = new HashMap<>();
        headers.put("x-apikey", apiKey.trim());
        JSONObject raw = new JSONObject(get(url, headers));
        JSONArray services = raw.optJSONArray("trainServices");
        // Some gateway response versions wrap the departure board in a result object.
        if (services == null) {
            JSONObject nested = raw.optJSONObject("GetDepartureBoardResult");
            if (nested == null) nested = raw.optJSONObject("stationBoard");
            if (nested != null) {
                services = nested.optJSONArray("trainServices");
                raw = nested;
            }
        }
        if (services == null) throw new Exception("Rail Data replied, but no departure-board data was returned.");
        JSONArray departures = new JSONArray();
        for (int i = 0; i < Math.min(8, services.length()); i++) {
            JSONObject service = services.optJSONObject(i);
            if (service == null) continue;
            String destination = "Unknown destination";
            JSONArray dests = service.optJSONArray("destination");
            if (dests != null && dests.length() > 0) {
                JSONObject dest = dests.optJSONObject(0);
                if (dest != null) destination = dest.optString("locationName", destination);
            } else if (service.optJSONObject("destination") != null) {
                destination = service.optJSONObject("destination").optString("locationName", destination);
            }
            String etd = service.optString("etd", "");
            boolean cancelled = service.optBoolean("isCancelled", false)
                    || "cancelled".equalsIgnoreCase(etd);
            departures.put(new JSONObject()
                    .put("std", service.optString("std", ""))
                    .put("etd", etd)
                    .put("platform", service.optString("platform", ""))
                    .put("destination", destination)
                    .put("cancelled", cancelled));
        }
        return new JSONObject().put("station", station)
                .put("stationName", raw.optString("locationName", station))
                .put("services", departures);
    }

    // -----------------------------------------------------------------------------------------
    // NaPTAN — official stop/station reference cache
    // -----------------------------------------------------------------------------------------

    private static void cacheNaptanStopsAsync(Context context, JSONArray stops) {
        if (stops == null) return;
        List<String> areas = new ArrayList<>();
        for (int i = 0; i < stops.length() && areas.size() < 8; i++) {
            JSONObject stop = stops.optJSONObject(i); if (stop == null) continue;
            String area = atcoArea(stop.optString("id", ""));
            if (!area.isEmpty() && !areas.contains(area)) areas.add(area);
        }
        for (String area : areas) cacheNaptanAreaAsync(context, area);
    }

    private static void cacheNaptanAreaAsync(Context context, String atcoCode) {
        String area = atcoArea(atcoCode);
        if (area.isEmpty()) return;
        EXECUTOR.execute(() -> {
            try {
                File dir = new File(context.getCacheDir(), "transit/naptan");
                if (!dir.exists() && !dir.mkdirs()) return;
                File file = new File(dir, area + ".csv");
                if (file.exists() && System.currentTimeMillis() - file.lastModified() < NAPTAN_MAX_AGE_MS) return;
                String url = "https://naptan.api.dft.gov.uk/v1/access-nodes?atcoAreaCodes=" + Uri.encode(area) + "&dataFormat=csv";
                byte[] data = getBytes(url);
                if (data.length < 32) return;
                try (FileOutputStream out = new FileOutputStream(file)) { out.write(data); }
            } catch (Exception ignored) {}
        });
    }

    private static String atcoArea(String code) {
        if (code == null) return "";
        String clean = code.trim();
        if (clean.length() >= 3 && Character.isDigit(clean.charAt(0)) && Character.isDigit(clean.charAt(1)) && Character.isDigit(clean.charAt(2)))
            return clean.substring(0, 3);
        return "";
    }

    // -----------------------------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------------------------

    private static boolean insideGreaterLondon(double lat, double lon) {
        // A deliberately broad cheap gate. TfL itself decides whether the actual points are valid.
        return lat >= 51.20 && lat <= 51.75 && lon >= -0.62 && lon <= 0.20;
    }


    /** TfL currently permits low-volume anonymous Unified API access. A configured key simply
     * raises the request allowance, so OpenRoad must not make London routing depend on it. */
    private static String tflKeyQuery(String key) {
        return has(key) ? "&app_key=" + Uri.encode(key.trim()) : "";
    }

    private static JSONObject nestedPlace(JSONObject point) {
        if (point == null) return new JSONObject();
        JSONObject place = point.optJSONObject("place");
        return place == null ? point : place;
    }

    private static boolean modeEnabled(JSONObject settings, String mode) {
        if (settings == null) return true;
        JSONObject modes = settings.optJSONObject("modes");
        return modes == null || modes.optBoolean(mode, true);
    }

    private static boolean hasExplicitModeSelection(JSONObject settings) {
        return settings != null && settings.optJSONObject("modes") != null;
    }

    private static String tflModes(JSONObject settings) {
        List<String> modes = new ArrayList<>();
        if (modeEnabled(settings, "bus")) modes.add("public-bus");
        if (modeEnabled(settings, "coach")) modes.add("coach");
        if (modeEnabled(settings, "train")) { modes.add("train"); modes.add("overground"); }
        if (modeEnabled(settings, "tube")) { modes.add("tube"); modes.add("dlr"); }
        if (modeEnabled(settings, "tram")) modes.add("tram");
        if (modeEnabled(settings, "ferry")) modes.add("river");
        if (modeEnabled(settings, "cablecar")) modes.add("cablecar");
        modes.add("walking");
        return joinComma(modes);
    }

    private static String transportApiModes(JSONObject settings) {
        if (settings == null || settings.optJSONObject("modes") == null) return "";
        List<String> modes = new ArrayList<>();
        if (modeEnabled(settings, "bus")) modes.add("bus");
        if (modeEnabled(settings, "coach")) modes.add("coach");
        if (modeEnabled(settings, "train")) modes.add("train");
        if (modeEnabled(settings, "tube")) modes.add("metro");
        if (modeEnabled(settings, "tram")) { modes.add("tram"); modes.add("light_rail"); }
        if (modeEnabled(settings, "ferry")) modes.add("ferry");
        return joinComma(modes);
    }

    private static String joinComma(List<String> values) {
        StringBuilder out = new StringBuilder();
        for (String value : values) { if (out.length() > 0) out.append(','); out.append(value); }
        return out.toString();
    }

    private static String normalizeMode(String mode) {
        String m = mode == null ? "" : mode.trim().toLowerCase(Locale.UK);
        if ("walking".equals(m) || "walk".equals(m)) return "foot";
        if ("national-rail".equals(m) || "rail".equals(m) || "overground".equals(m)) return "train";
        if ("subway".equals(m) || "underground".equals(m) || "metro".equals(m) || "dlr".equals(m)) return "tube";
        if ("light_rail".equals(m) || "light-rail".equals(m) || "light rail".equals(m)) return "tram";
        if ("river".equals(m) || "river-bus".equals(m)) return "ferry";
        if ("public-bus".equals(m)) return "bus";
        if ("cable-car".equals(m) || "cable car".equals(m)) return "cablecar";
        return m;
    }

    private static String legMessage(String mode, String line, String destination, String toName) {
        StringBuilder message = new StringBuilder();
        if ("foot".equals(mode)) message.append("Walk");
        else if ("bus".equals(mode)) message.append("Take bus").append(has(line) ? " " + line : "");
        else if ("train".equals(mode)) message.append("Take train").append(has(line) ? " " + line : "");
        else if (has(mode)) message.append("Take ").append(mode.replace('-', ' '));
        else message.append("Continue");
        if (has(destination)) message.append(" towards ").append(destination);
        if (has(toName)) message.append(" to ").append(toName);
        return message.toString();
    }

    private static String clock(String value) {
        if (!has(value)) return "";
        String v = value.trim();
        try { return OffsetDateTime.parse(v).format(DateTimeFormatter.ofPattern("HH:mm", Locale.UK)); }
        catch (Exception ignored) {}
        if (v.length() >= 5 && v.charAt(2) == ':') return v.substring(0, 5);
        return v;
    }

    private static long parseDurationSeconds(String value) {
        try {
            String[] bits = value.split(":");
            if (bits.length != 3) return 0;
            return Long.parseLong(bits[0]) * 3600L + Long.parseLong(bits[1]) * 60L + Long.parseLong(bits[2]);
        } catch (Exception e) { return 0; }
    }

    private static double pointsDistance(JSONArray points) {
        double total = 0.0, prevLat = Double.NaN, prevLon = Double.NaN;
        for (int i = 0; i < points.length(); i++) {
            JSONObject p = points.optJSONObject(i); if (p == null) continue;
            double lat = p.optDouble("latitude", Double.NaN), lon = p.optDouble("longitude", Double.NaN);
            if (Double.isFinite(prevLat) && Double.isFinite(lat)) total += distanceMetres(prevLat, prevLon, lat, lon);
            prevLat = lat; prevLon = lon;
        }
        return total;
    }

    private static double distanceMetres(double lat1, double lon1, double lat2, double lon2) {
        final double r=6371000.0;
        double p1=Math.toRadians(lat1), p2=Math.toRadians(lat2), dp=Math.toRadians(lat2-lat1), dl=Math.toRadians(lon2-lon1);
        double a=Math.sin(dp/2)*Math.sin(dp/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);
        return r*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
    }

    private static long ageMs(String timestamp) {
        if (!has(timestamp)) return -1L;
        try { return Math.abs(System.currentTimeMillis() - OffsetDateTime.parse(timestamp).toInstant().toEpochMilli()); }
        catch (Exception ignored) { return -1L; }
    }

    private static void addSource(List<String> sources, String source) {
        if (!sources.contains(source)) sources.add(source);
    }

    private static String joinSources(List<String> sources) {
        if (sources.isEmpty()) return "Official live data";
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < sources.size(); i++) { if (i > 0) out.append(" + "); out.append(sources.get(i)); }
        return out.toString();
    }

    private static boolean has(String value) { return value != null && !value.trim().isEmpty(); }

    private static String get(String url, Map<String,String> headers) throws Exception {
        HttpURLConnection connection = (HttpURLConnection)new URL(url).openConnection();
        connection.setConnectTimeout(12000); connection.setReadTimeout(18000);
        connection.setRequestProperty("Accept", "application/json, application/xml, text/xml, */*");
        connection.setRequestProperty("User-Agent", "OpenRoad-Android/0.6.27");
        if (headers != null) for (Map.Entry<String,String> e : headers.entrySet()) connection.setRequestProperty(e.getKey(), e.getValue());
        int status = connection.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder text = new StringBuilder();
        if (stream != null) try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line; while ((line = reader.readLine()) != null) text.append(line).append('\n');
        }
        connection.disconnect();
        if (status < 200 || status >= 300) {
            String detail = compactProviderError(text.toString());
            throw new Exception("Transport service returned HTTP " + status + (detail.isEmpty() ? "" : " · " + detail));
        }
        return text.toString();
    }

    private static String compactProviderError(String raw) {
        if (raw == null) return "";
        String text = raw.replaceAll("<[^>]+>", " ").replaceAll("\\s+", " ").trim();
        // Prefer common JSON error fields without ever echoing request URLs or credentials.
        try {
            JSONObject object = new JSONObject(raw);
            for (String key : new String[]{"error","message","detail","description"}) {
                String value = object.optString(key, "").trim();
                if (!value.isEmpty()) { text = value; break; }
            }
        } catch (Exception ignored) {}
        if (text.length() > 220) text = text.substring(0, 220) + "…";
        return text;
    }

    private static byte[] getBytes(String url) throws Exception {
        HttpURLConnection connection = (HttpURLConnection)new URL(url).openConnection();
        connection.setConnectTimeout(12000); connection.setReadTimeout(20000);
        connection.setRequestProperty("User-Agent", "OpenRoad-Android/0.6.27");
        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) { connection.disconnect(); throw new Exception("NaPTAN returned HTTP " + status); }
        try (InputStream in = connection.getInputStream(); java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int n; while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
            return out.toByteArray();
        } finally { connection.disconnect(); }
    }
}
