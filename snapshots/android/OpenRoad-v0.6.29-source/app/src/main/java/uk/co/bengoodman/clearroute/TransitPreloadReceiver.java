package uk.co.bengoodman.clearroute;

import android.Manifest;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import java.util.Calendar;
import java.util.concurrent.TimeUnit;

/** Lightweight once-daily regional-preparation check. It deliberately does nothing while
 * navigation is active: an en-route motorway location is not a useful preload destination. */
public final class TransitPreloadReceiver extends BroadcastReceiver {
    public static final String PREF_ENABLED = "daily_transit_preload";
    public static final String PREF_TRANSIT_NAV_ACTIVE = "transit_navigation_active";
    private static final String PREFS = "clearroute_local";

    public static void schedule(Context context) {
        AlarmManager am=(AlarmManager)context.getSystemService(Context.ALARM_SERVICE);if(am==null)return;
        Intent i=new Intent(context,TransitPreloadReceiver.class);PendingIntent pi=PendingIntent.getBroadcast(context,618,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Calendar c=Calendar.getInstance();c.set(Calendar.HOUR_OF_DAY,12);c.set(Calendar.MINUTE,5);c.set(Calendar.SECOND,0);c.set(Calendar.MILLISECOND,0);if(c.getTimeInMillis()<=System.currentTimeMillis())c.add(Calendar.DAY_OF_YEAR,1);
        am.setInexactRepeating(AlarmManager.RTC_WAKEUP,c.getTimeInMillis(),TimeUnit.DAYS.toMillis(1),pi);
    }
    public static void cancel(Context context){AlarmManager am=(AlarmManager)context.getSystemService(Context.ALARM_SERVICE);if(am==null)return;PendingIntent pi=PendingIntent.getBroadcast(context,618,new Intent(context,TransitPreloadReceiver.class),PendingIntent.FLAG_NO_CREATE|PendingIntent.FLAG_IMMUTABLE);if(pi!=null)am.cancel(pi);}

    @Override public void onReceive(Context context, Intent intent) {
        if(!context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getBoolean(PREF_ENABLED,true))return;
        if(ActiveRouteStore.exists(context) || context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getBoolean(PREF_TRANSIT_NAV_ACTIVE,false))return; // navigating: destination was already preloaded; do not prepare an en-route location.
        if(!OpenRoadServerClient.configured(context,BuildConfig.BUNDLED_OPENROAD_SERVER_URL))return;
        if(context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED && context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)!=PackageManager.PERMISSION_GRANTED)return;
        if(Build.VERSION.SDK_INT>=29 && context.checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION)!=PackageManager.PERMISSION_GRANTED)return;
        PendingResult pending=goAsync();
        try{
            LocationServices.getFusedLocationProviderClient(context).getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY,null)
                    .addOnSuccessListener(loc->{try{if(loc!=null)TransitClient.prepareServerRegion(context.getApplicationContext(),loc.getLatitude(),loc.getLongitude(),"daily-location");}finally{pending.finish();}})
                    .addOnFailureListener(e->pending.finish());
        }catch(Exception e){pending.finish();}
    }
}
