"""Strictly anchored Java adapter for v0.6.31 staged DEBUG research builds.

Never modifies production ZIP, signing, main, or live web/PHP endpoints.
"""
from __future__ import annotations
def replace_exact(s,old,new,label):
    n=s.count(old)
    if n!=1:raise ValueError(f"{label}: expected exactly one anchored source match, got {n}")
    return s.replace(old,new,1)

CLIENT= r'''
    // PT v2 reference handshake: accessible only to a DEBUG-gated caller.
    // Retains existing paired-device ECDSA signing, URL and API timeouts.
    public static JSONObject ptV2Issue(Context context, JSONObject query,
                                       String sessionId, int generation,
                                       String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject body=new JSONObject()
            .put("action","issue")
            .put("query",query)
            .put("sessionId",sessionId)
            .put("generation",generation);
        return postSigned(context,root+"/api/v2/task.php",
                          body.toString(),3000,6000);
    }
    public static JSONObject ptV2Route(Context context, JSONObject query,
                                       String ticket, String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject body=new JSONObject().put("action","route")
            .put("taskTicket",ticket).put("query",query);
        return postSigned(context,root+"/api/v2/task.php",
                          body.toString(),3000,6500);
    }
    public static JSONObject ptV2Cancel(Context context, String ticket,
                                        String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject body=new JSONObject().put("action","cancel")
            .put("taskTicket",ticket);
        return postSigned(context,root+"/api/v2/task.php",
                          body.toString(),2500,3500);
    }
    public static JSONObject ptV2Status(Context context, String ticket,
                                        String baseUrl) throws Exception {
        String root=requirePaired(context,baseUrl);
        JSONObject body=new JSONObject().put("action","status")
            .put("taskTicket",ticket);
        return postSigned(context,root+"/api/v2/task.php",
                          body.toString(),2500,3500);
    }
'''
LIFECYCLE=r'''
    // Strictly limited to debug-only v2 research requests. Never attempt
    // to cancel unrelated server work, shared cache tasks or v1 requests.
    private static final class V2Task {
        final Context context;
        final String ticket;
        final String url;
        V2Task(Context c,String t,String u) {
            context=c.getApplicationContext();ticket=t;url=u;
        }
    }
    private static final AtomicReference<V2Task> ACTIVE_V2 = new AtomicReference<>();
    private static final java.util.concurrent.ThreadPoolExecutor V2_CANCEL_EXECUTOR =
        new java.util.concurrent.ThreadPoolExecutor(
            1,1,0L,TimeUnit.MILLISECONDS,
            new java.util.concurrent.ArrayBlockingQueue<Runnable>(8),
            r -> {Thread t=new Thread(r,"OpenRoad-v2-cancel");t.setDaemon(true);return t;},
            new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
    private static void submitV2Cancel(V2Task task){
        if(task==null)return;
        try {
            V2_CANCEL_EXECUTOR.execute(() -> {
                try {
                    JSONObject reply=OpenRoadServerClient.ptV2Cancel(
                        task.context,task.ticket,task.url);
                    String state=reply.optString("remoteJobStatus","UNKNOWN");
                    Log.i(TIMING_TAG,"pt_v2_cancel_ack="+state);
                }catch(Exception e){
                    Log.w(TIMING_TAG,"pt_v2_cancel_remote_status_unknown");
                }
            });
        }catch(java.util.concurrent.RejectedExecutionException e){
            Log.w(TIMING_TAG,"pt_v2_cancel_queue_full_remote_status_unknown");
        }
    }

    private static void researchV2Route(
            Context context,double fromLat,double fromLon,
            double destLat,double destLon,JSONObject settings,
            long generation,Callback callback)throws Exception {
        // The v2 route response is research ONLY. Never pass it to
        // onSuccess(), which would activate legacy selectable route cards.
        if(!BuildConfig.DEBUG)throw new IllegalStateException("Debug research only");
        String url=BuildConfig.BUNDLED_OPENROAD_SERVER_URL;
        if(!OpenRoadServerClient.configured(context,url))
            throw new Exception("OpenRoad server is not configured.");
        JSONObject options=new JSONObject()
            .put("maxWalk",10)
            .put("walkSpeed",settings.optString("walkSpeed","normal"))
            .put("transferBuffer",settings.optString("transferBuffer","normal"))
            .put("ranking",settings.optString("ranking","balanced"))
            .put("phase","fast");
        JSONObject query=new JSONObject()
            .put("from",new JSONObject().put("lat",fromLat).put("lon",fromLon))
            .put("to",new JSONObject().put("lat",destLat).put("lon",destLon))
            .put("settings",options);
        if(routeWorkCancelled(generation))return;
        JSONObject issued=OpenRoadServerClient.ptV2Issue(
            context,query,java.util.UUID.randomUUID().toString(),
            (int)Math.min(generation,Integer.MAX_VALUE),url);
        String ticket=issued.optString("taskTicket","");
        if(!"OK".equals(issued.optString("outcome"))||ticket.isEmpty())
            throw new Exception("v2 timetable research unavailable");
        V2Task task=new V2Task(context,ticket,url);
        if(routeWorkCancelled(generation)){
            submitV2Cancel(task);return;
        }
        V2Task previous=ACTIVE_V2.getAndSet(task);
        if(previous!=null)submitV2Cancel(previous);
        try{
            if(routeWorkCancelled(generation))return;
            JSONObject result=OpenRoadServerClient.ptV2Route(
                context,query,ticket,url);
            if(routeWorkCancelled(generation))return;
            String outcome=result.optString("outcome","PROVIDER_UNAVAILABLE");
            Log.i(TIMING_TAG,"pt_v2_research_outcome="+outcome);
            callback.onError("PT v2 research completed ("+outcome+
                "). Journeys are disabled pending verified walking access.");
        }finally{
            // If cancelled meanwhile, cancellation is scheduled by
            // cancelRouteWork(). Never interpret a client abort as STOPPED.
            if(ACTIVE_V2.compareAndSet(task,null) &&
               routeWorkCancelled(generation))submitV2Cancel(task);
        }
    }
'''

def patch_server(java):
    point="    public static JSONObject busService(Context context, String line, double lat, double lon, String baseUrl) throws Exception {"
    return replace_exact(java,point,CLIENT+"\n"+point,"server signed v2 methods")

def patch_transit(java):
    marker="    private static final long NAPTAN_MAX_AGE_MS ="
    java=replace_exact(java,marker,LIFECYCLE+"\n"+marker,"research lifecycle insertion")
    marker="            Future<?> f = ACTIVE_ROUTE_TASK.getAndSet(null);"
    java=replace_exact(java,marker,
        "            V2Task activeV2 = ACTIVE_V2.getAndSet(null);\n"
        "            if(activeV2!=null)submitV2Cancel(activeV2);\n"
        +marker,"native cancel to remote bridge")
    needle='            progress(guarded, "Searching public transport timetables…", startMs);'
    n=java.count(needle)
    if n!=2: raise ValueError(f"transit route entry: expected two entrypoints, got {n}")
    # Both route() and routeWithStops() use this point; the debug branch
    # is explicit and not included in any default UI setting.
    insertion=needle+'''
            if(BuildConfig.DEBUG && settings!=null &&
               settings.optBoolean("ptV2Research",false)){
                try{
                    researchV2Route(context,originLat,originLon,
                        destLat,destLon,settings,token,guarded);
                }catch(Exception researchError){
                    if(!routeWorkCancelled(token))
                        guarded.onError("PT v2 research endpoint unavailable.");
                }
                return;
            }'''
    java=java.replace(needle,insertion)
    # The legacy API supports routeWithStops, but the v2 pilot has not
    # validated via-stop identity/transfer stitching. Reject rather than
    # silently ignoring any intermediate stops.
    split_at="    public static void routeWithStops("
    if java.count(split_at)!=1:
        raise ValueError("Ambiguous transit via-stop method")
    start=java.index(split_at)
    head,tail=java[:start],java[start:]
    debug_entry='''if(BuildConfig.DEBUG && settings!=null &&
               settings.optBoolean("ptV2Research",false)){
                try{'''
    if tail.count(debug_entry)!=1:
        raise ValueError("Unexpected v2 via-stop research branch")
    tail=tail.replace(debug_entry,'''if(BuildConfig.DEBUG && settings!=null &&
               settings.optBoolean("ptV2Research",false)){
                if(viaStops!=null && viaStops.length()>0){
                    guarded.onError("PT v2 research does not yet support added stops.");
                    return;
                }
                try{''',1)
    return head+tail
