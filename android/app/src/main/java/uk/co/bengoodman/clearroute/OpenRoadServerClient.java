package uk.co.bengoodman.clearroute;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Authenticated client for the owner's private OpenRoad transport server.
 * Requests are HTTPS POSTs signed by a non-exportable Android Keystore EC key.
 */
public final class OpenRoadServerClient {
    private OpenRoadServerClient() {}

    public static boolean configured(Context context, String baseUrl) {
        String url = DeviceAuth.normaliseBaseUrl(baseUrl);
        return url.startsWith("https://") && DeviceAuth.isPaired(context, url);
    }

    public static JSONObject pair(Context context, String baseUrl, String pairingCode) throws Exception {
        String root = requireHttpsBase(baseUrl);
        String code = pairingCode == null ? "" : pairingCode.trim();
        if (code.isEmpty()) throw new Exception("Enter the one-time pairing code from your server.");
        JSONObject body = new JSONObject();
        body.put("pairingCode", code);
        body.put("deviceId", DeviceAuth.deviceId(context));
        body.put("publicKeyPem", DeviceAuth.publicKeyPem());
        body.put("deviceLabel", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL);
        JSONObject reply = postUnsigned(root + "/api/v1/pair.php", body.toString(), 5000, 8000);
        if (!reply.optBoolean("ok", false)) throw new Exception(reply.optString("error", "Pairing failed"));
        DeviceAuth.markPaired(context, root);
        return reply;
    }

    public static JSONObject status(Context context, String baseUrl) throws Exception {
        String root = requirePaired(context, baseUrl);
        return postSigned(context, root + "/api/v1/status.php", "{}", 4500, 7000);
    }

    /** Server-managed Rail Data. The consumer key never travels to or from Android. */
    public static JSONObject railDepartureBoard(Context context, String stationCode, String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        String code=stationCode==null?"":stationCode.trim().toUpperCase(java.util.Locale.UK);
        if(!code.matches("[A-Z]{3}"))throw new Exception("Enter a three-letter station code.");
        JSONObject request=new JSONObject().put("station",code);
        return postSigned(context,root+"/api/v1/rail.php",request.toString(),3000,5500);
    }

    /** On-demand BODS SIRI-VM via the paired private server: no BODS credential on Android. */
    public static String bodsLiveXml(Context context, String line, double lat, double lon, String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        if (!Double.isFinite(lat) || !Double.isFinite(lon)) throw new Exception("Invalid map location");
        String clean=line==null?"":line.trim();
        if (!clean.matches("[A-Za-z0-9 _-]{1,12}")) throw new Exception("Invalid bus line");
        JSONObject body=new JSONObject().put("line",clean).put("lat",lat).put("lon",lon);
        JSONObject json=postSigned(context,root+"/api/v1/bods.php",body.toString(),3000,5500);
        String xml=json.optString("xml","");
        if (xml.isEmpty() || xml.length()>262144) throw new Exception("BODS returned no usable live data");
        return xml;
    }

    public static JSONObject route(Context context,
                                   double originLat, double originLon,
                                   double destLat, double destLon,
                                   JSONObject settings,
                                   String baseUrl) throws Exception {
        String root = requirePaired(context, baseUrl);
        JSONObject body = new JSONObject();
        body.put("from", new JSONObject().put("lat", originLat).put("lon", originLon));
        body.put("to", new JSONObject().put("lat", destLat).put("lon", destLon));
        JSONObject safe = settings == null ? new JSONObject() : settings;
        body.put("settings", new JSONObject()
                .put("maxWalk", 999)
                .put("walkSpeed", safe.optString("walkSpeed", "normal"))
                .put("transferBuffer", safe.optString("transferBuffer", "normal"))
                .put("ranking", safe.optString("ranking", "balanced"))
                .put("resultLimit", 3)
                .put("phase", "fast".equals(safe.optString("serverPhase", "full")) ? "fast" : "full"));
        JSONObject json = postSigned(context, root + "/api/v1/journeys.php", body.toString(), 3000, 6000);
        if (json.optJSONArray("routes") == null || json.optJSONArray("routes").length() == 0)
            throw new Exception("OpenRoad transport server returned no journeys");
        return json;
    }

    private static String lastMixedKey="";
    private static String lastMixedResponse="";
    private static long lastMixedAt=0L;

    /**
     * Timetable-verified bus → train → bus itineraries are assembled server-side.
     * Signed API, bounded geocoding-free requests. Cache only within this process
     * to avoid duplicate fast/full calls, never persist someone's journey.
     */
    public static JSONObject multimodalJourneys(Context context,double a,double b,double c,double d,
                                                JSONObject settings,String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject safe=settings==null?new JSONObject():settings;
        String walking=safe.optString("walkSpeed","normal");
        String transfer=safe.optString("transferBuffer","normal");
        String key=Math.round(a*100000)+":"+Math.round(b*100000)+":"+
                   Math.round(c*100000)+":"+Math.round(d*100000)+":"+walking+":"+transfer;
        long now=android.os.SystemClock.elapsedRealtime();
        synchronized(OpenRoadServerClient.class){
            if(key.equals(lastMixedKey)&&now-lastMixedAt>=0&&now-lastMixedAt<45000&&!lastMixedResponse.isEmpty())
                return new JSONObject(lastMixedResponse);
        }
        JSONObject body=new JSONObject()
            .put("from",new JSONObject().put("lat",a).put("lon",b))
            .put("to",new JSONObject().put("lat",c).put("lon",d))
            .put("settings",new JSONObject().put("walkSpeed",walking).put("transferBuffer",transfer)
                     .put("maxWalkMeters",1600));
        JSONObject response=postSigned(context,root+"/api/v1/multimodal.php",body.toString(),2500,9500);
        JSONArray routes=response.optJSONArray("routes");
        if(routes==null||routes.length()==0)throw new Exception("No verified bus-and-train connections");
        for(int i=0;i<routes.length();i++){
            JSONObject route=routes.optJSONObject(i);
            if(route==null||!route.optBoolean("clearRouteMultimodal",false))
                throw new Exception("Invalid multimodal response");
            JSONArray legs=route.optJSONArray("transitLegs"),geometry=route.optJSONArray("legs");
            if(legs==null||geometry==null||legs.length()!=geometry.length())
                throw new Exception("Multimodal geometry mismatch");
        }
        synchronized(OpenRoadServerClient.class){
            lastMixedKey=key;lastMixedResponse=response.toString();lastMixedAt=now;
        }
        return response;
    }

    /** Timetable-only national railway planning. Signed like every private OpenRoad request. */
    public static JSONObject railJourneys(Context context, double fromLat, double fromLon,
                                          double toLat, double toLon, String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject body=new JSONObject()
                .put("from",new JSONObject().put("lat",fromLat).put("lon",fromLon))
                .put("to",new JSONObject().put("lat",toLat).put("lon",toLon));
        JSONObject result=postSigned(context,root+"/api/v1/rail_journeys.php",body.toString(),2500,5500);
        JSONArray routes=result.optJSONArray("routes");
        if(routes==null||routes.length()==0)throw new Exception("No scheduled rail journeys found");
        return result;
    }

    public static JSONObject busService(Context context, String line, double lat, double lon, String baseUrl) throws Exception {
        String root = requirePaired(context, baseUrl);
        JSONObject body = new JSONObject().put("line", line == null ? "" : line.trim()).put("lat", lat).put("lon", lon);
        JSONObject json = postSigned(context, root + "/api/v1/service.php", body.toString(), 4500, 8000);
        if (json.optJSONArray("geometries") == null || json.optJSONArray("geometries").length() == 0)
            throw new Exception("OpenRoad transport server returned no bus route geometry");
        return json;
    }


    public static JSONObject prepareRegion(Context context, double lat, double lon, String reason, String baseUrl) throws Exception {
        String root = requirePaired(context, baseUrl);
        JSONObject body = new JSONObject().put("lat", lat).put("lon", lon).put("reason", reason == null ? "destination" : reason);
        return postSigned(context, root + "/api/v1/prepare.php", body.toString(), 3500, 6000);
    }

    public static JSONObject busStop(Context context, String stopId, double lat, double lon, String baseUrl) throws Exception {
        String root = requirePaired(context, baseUrl);
        JSONObject body = new JSONObject().put("stopId", stopId == null ? "" : stopId.trim()).put("lat", lat).put("lon", lon);
        return postSigned(context, root + "/api/v1/stop.php", body.toString(), 3500, 6500);
    }

    public static boolean revokeThisDevice(Context context, String baseUrl) {
        try {
            String root = requirePaired(context, baseUrl);
            JSONObject r = postSigned(context, root + "/api/v1/revoke.php", "{}", 4500, 7000);
            if (!r.optBoolean("ok", false)) return false;
            DeviceAuth.clearPairing(context);
            return true;
        } catch (Exception ignored) { return false; }
    }

    private static String requireHttpsBase(String baseUrl) throws Exception {
        String root = DeviceAuth.normaliseBaseUrl(baseUrl);
        if (!root.startsWith("https://")) throw new Exception("OpenRoad server must use HTTPS.");
        return root;
    }

    private static String requirePaired(Context context, String baseUrl) throws Exception {
        String root = requireHttpsBase(baseUrl);
        if (!DeviceAuth.isPaired(context, root)) throw new Exception("OpenRoad transport server is not paired to this device.");
        return root;
    }

    private static JSONObject postUnsigned(String url, String body, int connectTimeout, int readTimeout) throws Exception {
        HttpURLConnection c = connection(url, connectTimeout, readTimeout);
        write(c, body);
        return response(c);
    }

    private static JSONObject postSigned(Context context, String url, String body, int connectTimeout, int readTimeout) throws Exception {
        URL u = new URL(url);
        long ts = System.currentTimeMillis() / 1000L;
        String nonce = DeviceAuth.nonce();
        String device = DeviceAuth.deviceId(context);
        String canonical = "OPENROAD1\nPOST\n" + u.getPath() + "\n" + ts + "\n" + nonce + "\n" + device + "\n" + sha256(body);
        String signature = DeviceAuth.sign(canonical);
        HttpURLConnection c = connection(url, connectTimeout, readTimeout);
        c.setRequestProperty("X-OpenRoad-Device", device);
        c.setRequestProperty("X-OpenRoad-Timestamp", Long.toString(ts));
        c.setRequestProperty("X-OpenRoad-Nonce", nonce);
        c.setRequestProperty("X-OpenRoad-Signature", signature);
        write(c, body);
        return response(c);
    }

    private static HttpURLConnection connection(String url, int connectTimeout, int readTimeout) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(connectTimeout);
        c.setReadTimeout(readTimeout);
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setInstanceFollowRedirects(false);
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("User-Agent", "OpenRoad-Android/0.6.29");
        return c;
    }

    private static void write(HttpURLConnection c, String body) throws Exception {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(bytes.length);
        try (OutputStream out = c.getOutputStream()) { out.write(bytes); }
    }

    private static JSONObject response(HttpURLConnection c) throws Exception {
        int code = c.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
        String body = read(in);
        c.disconnect();
        JSONObject json;
        try { json = new JSONObject(body); }
        catch (Exception e) { throw new Exception("OpenRoad transport server returned an invalid response (HTTP " + code + ")"); }
        if (code < 200 || code >= 300 || !json.optBoolean("ok", false)) {
            String detail = json.optString("error", "HTTP " + code);
            throw new Exception("OpenRoad transport server: " + detail);
        }
        return json;
    }

    private static String sha256(String value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder b = new StringBuilder(64);
        for (byte x : digest) b.append(String.format(java.util.Locale.ROOT, "%02x", x & 0xff));
        return b.toString();
    }

    private static String read(InputStream in) throws Exception {
        if (in == null) return "";
        StringBuilder b = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line; while ((line = r.readLine()) != null) b.append(line);
        }
        return b.toString();
    }
}
