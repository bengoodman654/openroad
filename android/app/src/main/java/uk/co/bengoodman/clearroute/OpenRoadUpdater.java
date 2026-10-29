package uk.co.bengoodman.clearroute;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Private GitHub Releases updater. Never installs without a user gesture and system confirmation. */
final class OpenRoadUpdater {
    private static final String RELEASE_API = "https://api.github.com/repos/bengoodman654/openroad/releases/latest";
    private static final String ALLOWED_PREFIX = "https://github.com/bengoodman654/openroad/releases/download/";
    private static final long CHECK_INTERVAL_MS = 24L * 60 * 60 * 1000;
    private static final int MAX_APK_BYTES = 150 * 1024 * 1024;
    private static final String PREFS = "openroad_updater";
    private final Activity activity;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile Release offered;
    private volatile File verifiedApk;
    private volatile boolean busy;

    static final class Release {
        int code;
        String name, url, sha256;
    }

    OpenRoadUpdater(Activity activity) { this.activity = activity; }

    void shutdown() { executor.shutdownNow(); }

    void check(boolean userInitiated) {
        SharedPreferences prefs = activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE);
        long now = System.currentTimeMillis();
        if (!userInitiated && now - prefs.getLong("last_check", 0L) < CHECK_INTERVAL_MS) return;
        if (busy) return;
        busy = true;
        send("checking", "Checking GitHub for updates…", null);
        executor.execute(() -> {
            try {
                JSONObject release = fetchJson(RELEASE_API);
                JSONObject manifest = null;
                org.json.JSONArray assets = release.optJSONArray("assets");
                for (int i=0; assets != null && i<assets.length(); i++) {
                    JSONObject a=assets.optJSONObject(i);
                    if (a != null && "update.json".equals(a.optString("name"))) {
                        String uri=a.optString("browser_download_url");
                        if (!uri.startsWith(ALLOWED_PREFIX)) throw new SecurityException("Unexpected manifest location");
                        manifest=fetchJson(uri); break;
                    }
                }
                if (manifest == null) throw new IllegalStateException("The latest GitHub release has no update.json");
                Release r=new Release();
                r.code=manifest.getInt("versionCode");
                r.name=manifest.getString("versionName");
                r.url=manifest.getString("apkUrl");
                r.sha256=manifest.getString("sha256").toLowerCase(java.util.Locale.ROOT);
                if (!"uk.co.bengoodman.clearroute".equals(manifest.getString("applicationId")) ||
                    !r.url.startsWith(ALLOWED_PREFIX) ||
                    !r.sha256.matches("[a-f0-9]{64}") ||
                    r.code<=0) throw new SecurityException("Invalid update manifest");
                // Ensure the signed release's manifest points to an asset in this release.
                boolean assetFound=false;
                for (int i=0; assets != null && i<assets.length(); i++) {
                    JSONObject a=assets.optJSONObject(i);
                    if (a != null && r.url.equals(a.optString("browser_download_url"))) assetFound=true;
                }
                if (!assetFound) throw new SecurityException("Update APK is not attached to this release");
                prefs.edit().putLong("last_check",System.currentTimeMillis()).apply();
                int installed = BuildConfig.VERSION_CODE;
                if (r.code>installed) {
                    offered=r;
                    verifiedApk=null;
                    send("available", "OpenRoad " + r.name + " is available", r.name);
                } else {
                    offered=null;
                    verifiedApk=null;
                    if (userInitiated) send("current", "OpenRoad is up to date (" + BuildConfig.VERSION_NAME + ")", BuildConfig.VERSION_NAME);
                    else send("idle", "", null);
                }
            } catch (Exception e) {
                Log.w("OpenRoadUpdater", "Update check failed: " + e.getClass().getSimpleName());
                send(userInitiated?"error":"idle", userInitiated?"Couldn't check for updates. Try again later.":"", null);
            } finally {busy=false;}
        });
    }

    void install() {
        final Release release=offered;
        if (release==null) { send("error","Check for updates first.", null); return; }
        if (busy) return;
        if (verifiedApk!=null && verifiedApk.isFile()) {
            try { if (matchesSha256(verifiedApk, release.sha256)) { offerInstaller(verifiedApk); return; } }
            catch (Exception ignored) {}
            verifiedApk.delete();verifiedApk=null;
        }
        busy=true;
        send("downloading", "Downloading OpenRoad " + release.name + "…", release.name);
        executor.execute(() -> {
            File out = new File(activity.getCacheDir(), "openroad-update.apk");
            File temp = new File(activity.getCacheDir(), "openroad-update.pending.apk");
            try {
                HttpURLConnection conn = open(release.url);
                int size=conn.getContentLength();
                if (size>MAX_APK_BYTES) throw new SecurityException("Update is too large");
                int bytes=0;
                MessageDigest md=MessageDigest.getInstance("SHA-256");
                try (InputStream in=conn.getInputStream();FileOutputStream fos=new FileOutputStream(temp)) {
                    byte[] buffer=new byte[32768];int read;
                    while((read=in.read(buffer))!=-1) {
                        bytes+=read;
                        if(bytes>MAX_APK_BYTES) throw new SecurityException("Update exceeds size limit");
                        md.update(buffer,0,read);fos.write(buffer,0,read);
                    }
                    fos.getFD().sync();
                } finally {conn.disconnect();}
                if (!hex(md.digest()).equals(release.sha256)) throw new SecurityException("Update checksum mismatch");
                // Do not present APKs signed by an unexpected key, including the initial debug-key transition.
                if (!matchesInstalledSignature(temp)) throw new SecurityException("Update uses a different app signing key. A one-time migration may be needed.");
                if (out.exists() && !out.delete()) throw new Exception("Cannot replace cached update");
                if (!temp.renameTo(out)) throw new Exception("Cannot finalise cached update");
                verifiedApk=out;
                activity.runOnUiThread(() -> offerInstaller(out));
            } catch (Exception e) {
                temp.delete();
                Log.w("OpenRoadUpdater", "Download rejected: " + e.getClass().getSimpleName());
                send("error", "Update couldn't be installed: " + e.getMessage(), null);
            } finally {busy=false;}
        });
    }

    private boolean matchesInstalledSignature(File apk) throws Exception {
        PackageManager pm=activity.getPackageManager();
        int flag=Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo file=pm.getPackageArchiveInfo(apk.getAbsolutePath(),flag);
        PackageInfo live=pm.getPackageInfo(activity.getPackageName(),flag);
        if (file==null || file.packageName==null || !file.packageName.equals(live.packageName)) return false;
        Signature[] a=Build.VERSION.SDK_INT>=28?file.signingInfo.getApkContentsSigners():file.signatures;
        Signature[] b=Build.VERSION.SDK_INT>=28?live.signingInfo.getApkContentsSigners():live.signatures;
        return a!=null && b!=null && a.length==1 && b.length==1 && MessageDigest.isEqual(a[0].toByteArray(),b[0].toByteArray());
    }

    private void offerInstaller(File file) {
        try {
            if (Build.VERSION.SDK_INT>=26 && !activity.getPackageManager().canRequestPackageInstalls()) {
                send("permission", "Allow OpenRoad to install updates in Android settings, then return and tap Install.",offered.name);
                Intent settings=new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:"+activity.getPackageName()));
                activity.startActivity(settings);
                return;
            }
            Uri uri=FileProvider.getUriForFile(activity,activity.getPackageName()+".updates",file);
            Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(intent);
            send("ready", "Confirm the update in Android's installer.",offered.name);
        } catch (Exception e) {send("error","Couldn't open Android's installer.",null);}
    }

    private static HttpURLConnection open(String uri) throws Exception {
        if(!uri.startsWith("https://")) throw new SecurityException("HTTPS required");
        URL url=new URL(uri);
        HttpURLConnection conn=(HttpURLConnection)url.openConnection();
        conn.setConnectTimeout(6500);conn.setReadTimeout(12000);
        conn.setRequestProperty("User-Agent","OpenRoad-Android-Updater");
        conn.setRequestProperty("Accept","application/vnd.github+json");
        if(conn.getResponseCode()!=200) {int status=conn.getResponseCode();conn.disconnect();throw new Exception("HTTP "+status);}
        return conn;
    }

    private static JSONObject fetchJson(String uri) throws Exception {
        HttpURLConnection conn=open(uri);
        try(InputStream in=conn.getInputStream()) {
            byte[] b=new byte[8192];java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();int n;
            while((n=in.read(b))!=-1){if(out.size()+n>512*1024)throw new SecurityException("Manifest too large");out.write(b,0,n);}
            return new JSONObject(out.toString("UTF-8"));
        } finally {conn.disconnect();}
    }
    private static String hex(byte[] bytes) {
        StringBuilder sb=new StringBuilder(bytes.length*2);
        for(byte b:bytes)sb.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return sb.toString();
    }
    private static boolean matchesSha256(File f,String expected) throws Exception {
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        try(InputStream in=new FileInputStream(f)){byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1)md.update(b,0,n);}
        return hex(md.digest()).equals(expected);
    }
    private void send(String state,String message,String version) {
        JSONObject data=new JSONObject();
        try {data.put("state",state);data.put("message",message);data.put("version",version==null?JSONObject.NULL:version);}catch(Exception ignored){}
        String script="window.ClearRoute && ClearRoute.onUpdateStatus && ClearRoute.onUpdateStatus("+data+")";
        activity.runOnUiThread(() -> {
            if(activity instanceof MainActivity) ((MainActivity)activity).deliverUpdateScript(script);
        });
    }
}
