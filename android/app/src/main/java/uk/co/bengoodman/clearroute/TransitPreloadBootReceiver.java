package uk.co.bengoodman.clearroute;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Restores the once-daily regional preparation alarm after a phone reboot or app update. */
public final class TransitPreloadBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!context.getSharedPreferences("clearroute_local", Context.MODE_PRIVATE)
                .getBoolean(TransitPreloadReceiver.PREF_ENABLED, true)) return;
        TransitPreloadReceiver.schedule(context.getApplicationContext());
    }
}
