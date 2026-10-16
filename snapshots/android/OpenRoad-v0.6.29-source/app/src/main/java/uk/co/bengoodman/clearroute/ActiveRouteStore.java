package uk.co.bengoodman.clearroute;

import android.content.Context;

import org.json.JSONObject;

import java.io.File;

/**
 * Stores only the route that is currently being navigated.
 *
 * The file lives in Android's cache directory rather than permanent app storage and
 * expires automatically. This gives the foreground navigation service enough state to
 * survive process recreation without turning the file into route history.
 */
public final class ActiveRouteStore {
    private static final String FILE_NAME = "active_route.json";
    private static final String SAVED_AT = "_savedAt";
    private static final long MAX_AGE_MS = 12L * 60L * 60L * 1000L;

    private ActiveRouteStore() {}

    private static File file(Context context) {
        return new File(context.getCacheDir(), FILE_NAME);
    }

    private static File legacyFile(Context context) {
        return new File(context.getFilesDir(), FILE_NAME);
    }

    private static void cleanupLegacy(Context context) {
        try {
            File legacy = legacyFile(context);
            if (legacy.exists()) legacy.delete();
        } catch (Exception ignored) {}
    }

    public static synchronized void save(Context context, JSONObject state) throws Exception {
        cleanupLegacy(context);
        state.put(SAVED_AT, System.currentTimeMillis());
        LocalFiles.writeUtf8(file(context), state.toString());
    }

    public static synchronized JSONObject load(Context context) {
        cleanupLegacy(context);
        try {
            File file = file(context);
            if (!file.exists()) return null;
            JSONObject state = new JSONObject(LocalFiles.readUtf8(file));
            long savedAt = state.optLong(SAVED_AT, 0L);
            if (savedAt <= 0L || System.currentTimeMillis() - savedAt > MAX_AGE_MS) {
                file.delete();
                return null;
            }
            return state;
        } catch (Exception ignored) {
            clear(context);
            return null;
        }
    }

    public static synchronized boolean exists(Context context) {
        return load(context) != null;
    }

    public static synchronized void clear(Context context) {
        cleanupLegacy(context);
        try {
            File file = file(context);
            if (file.exists()) file.delete();
        } catch (Exception ignored) {}
    }
}
