"""Isolated, source-pinned multiple-trip direct-bus prototype (NOT production).

Reads only validated, explicitly scoped Coventry TXC candidate snapshots. Supports
one transit leg, precise ATCO stop IDs, direction, boarding and alighting rules.
No walking connectors, transfers, live data, Android, or bank-holiday generality.
"""
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from coventry_11_multitrip import APPROVED_DATES,UnsupportedTXC

BOARD={"pickUp","pickUpAndSetDown"}
ALIGHT={"setDown","pickUpAndSetDown"}
PIN="5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0"

def _depart_seconds(value):
    h,m,s=(int(x) for x in value.split(":"))
    if not (0<=h<=99 and 0<=m<60 and 0<=s<60):
        raise UnsupportedTXC("Bad trip departure time")
    return 3600*h+60*m+s

def _trip_times(snapshot,trip,board,alight):
    tz=ZoneInfo(snapshot["time_zone"])
    day=date.fromisoformat(snapshot["service_date"])
    midnight_local=datetime.combine(day,time.min,tz)
    origin_utc=midnight_local.astimezone(timezone.utc)
    shift=_depart_seconds(trip["published_departure_time"])
    dep=(origin_utc+timedelta(seconds=shift+board["departure_offset_seconds"])).astimezone(tz)
    arr=(origin_utc+timedelta(seconds=shift+alight["arrival_offset_seconds"])).astimezone(tz)
    if arr<=dep:raise UnsupportedTXC("Non-positive journey duration")
    # Clock changes are explicitly NOT supported in this limited test engine.
    if dep.utcoffset()!=arr.utcoffset():raise UnsupportedTXC("Crosses DST transition")
    return dep,arr

def validate(snapshot):
    if snapshot.get("kind")!="REAL_TXC_MULTITRIP_OFFLINE_CANDIDATES":
        raise UnsupportedTXC("Unapproved fixture type")
    if (snapshot.get("source_zip_sha256"),snapshot.get("operator_noc"),snapshot.get("line"),
        snapshot.get("service_code"),snapshot.get("source_dataset"))!=(PIN,"TCVW","11","PD0001111:813","20442"):
        raise UnsupportedTXC("Source or operator identity mismatch")
    if snapshot.get("time_zone")!="Europe/London" or snapshot.get("service_date") not in APPROVED_DATES:
        raise UnsupportedTXC("Unknown date/timezone")
    trips=snapshot.get("trips",[])
    if not isinstance(trips,list) or len(trips)>700:raise UnsupportedTXC("Unexpected trip set")
    ids=set()
    for t in trips:
        code=t.get("journey_code")
        if not code or code in ids:raise UnsupportedTXC("Duplicate or missing trip")
        ids.add(code)
        times=t.get("stops",[])
        if not isinstance(times,list) or not 2<=len(times)<=150:raise UnsupportedTXC("Invalid stop count")
        last=-1
        for stop in times:
            arr=stop.get("arrival_offset_seconds")
            dep=stop.get("departure_offset_seconds")
            if not isinstance(arr,int) or not isinstance(dep,int) or arr<last or dep<arr:
                raise UnsupportedTXC("Non-monotonic stop timing")
            if stop.get("activity") not in BOARD|ALIGHT|{"pass"}:
                raise UnsupportedTXC("Invalid stop activity")
            last=dep
    return trips

def direct_options(snapshot,origin_ref,dest_ref,depart_after,max_results=3):
    if depart_after.tzinfo is None:raise UnsupportedTXC("Use timezone-aware query")
    if not 1<=max_results<=3:raise UnsupportedTXC("Unsupported result limit")
    trips=validate(snapshot)
    # Do not claim correctness on the UK autumn clock-change service day.
    if snapshot["service_date"]=="2026-10-25":
        return {"outcome":"UNSUPPORTED_CALENDAR_TIME_TRANSITION","results":[],
                "reason":"UK autumn DST service-day semantics not independently validated"}
    if not origin_ref or not dest_ref or origin_ref==dest_ref:
        return {"outcome":"INPUT_INVALID","results":[]}
    candidates=[]
    for t in trips:
        stoplist=t["stops"]
        for i,b in enumerate(stoplist[:-1]):
            if b["stop_ref"]!=origin_ref or b["activity"] not in BOARD:continue
            for j in range(i+1,len(stoplist)):
                e=stoplist[j]
                if e["stop_ref"]!=dest_ref or e["activity"] not in ALIGHT:continue
                try:departure,arrival=_trip_times(snapshot,t,b,e)
                except UnsupportedTXC:continue
                if departure<depart_after:continue
                candidates.append({
                    "trip_occurrence_id":f'TCVW:PD0001111:813:{t["journey_code"]}:{snapshot["service_date"]}',
                    "line":"11","direction":t["direction"],
                    "origin_stop":origin_ref,"destination_stop":dest_ref,
                    "departure":departure.isoformat(),"arrival":arrival.isoformat(),
                    "duration_seconds":int((arrival-departure).total_seconds()),
                    "stops_between":j-i-1,
                    "source_snapshot":snapshot["source_zip_sha256"],
                    "verification":"SOURCE_DERIVED_MULTITRIP_OFFLINE_ONLY"
                })
    candidates.sort(key=lambda x:(x["arrival"],x["departure"],x["trip_occurrence_id"]))
    # Collapse equivalent published departures, preserving all original IDs.
    groups={}
    for c in candidates:
        signature=c.pop("_signature")
        if signature in groups:
            groups[signature]["source_trip_aliases"].append(c["trip_occurrence_id"])
        else:
            c["source_trip_aliases"]=[c["trip_occurrence_id"]]
            groups[signature]=c
    options=sorted(groups.values(),
        key=lambda c:(c["arrival"],c["departure"],c["trip_occurrence_id"]))[:max_results]
    return {"outcome":"OK" if options else "NO_JOURNEY",
            "results":options,"source_snapshot":snapshot["source_zip_sha256"],
            "service_date":snapshot["service_date"],
            "origin_stop":origin_ref,"destination_stop":dest_ref}
