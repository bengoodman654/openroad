"""Tiny OFFLINE direct-bus prototype over ONE immutable, published source-derived fixture.

Not the proposed multimodal planner, Android application, or PHP server.
A correct result proves internal trip matching only; it does not prove nationwide
coverage or independent publisher validity. No network or third-party APIs.
"""
from datetime import datetime,date,time,timedelta,timezone
from zoneinfo import ZoneInfo

BOARD={"pickUp","pickUpAndSetDown"}
ALIGHT={"setDown","pickUpAndSetDown"}
EXPECTED_KIND="REAL_TXC_COVENTRY_11_CANDIDATE_NOT_INDEPENDENTLY_VERIFIED"

class FixtureError(ValueError):pass

def validate(f):
    if f.get("kind")!=EXPECTED_KIND or f.get("operator_noc")!="TCVW" or f.get("line")!="11":
        raise FixtureError("Unapproved provenance")
    if f.get("weekday")!="Friday" or f.get("service_date")!="2026-10-23":
        raise FixtureError("Fixture date outside verified scope")
    if f.get("time_zone")!="Europe/London" or not f.get("source_zip_sha256"):
        raise FixtureError("Missing timezone or pinned source")
    j=f.get("journey",{})
    if not j.get("journey_code") or j.get("unhandled_special_rules") is not False:
        raise FixtureError("Unsupported calendar and trip conditions")
    stops=j.get("stops",[])
    if not 2<=len(stops)<=150:raise FixtureError("No usable stop sequence")
    previous=(-1,-1)
    for s in stops:
        if not isinstance(s.get("stop_ref"),str) or not s.get("name"):raise FixtureError("Missing stop reference")
        ar=s.get("arrival_offset_seconds");dep=s.get("departure_offset_seconds")
        if not isinstance(ar,int) or not isinstance(dep,int) or ar<0 or dep<ar or ar<previous[1]:
            raise FixtureError("Inconsistent source stop times")
        previous=(ar,dep)
    if not all(x in ("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday","MondayToFriday","MondayToSaturday","MondayToSunday") for x in j.get("regular_day_tokens",[])):
        raise FixtureError("Unrecognized operating rule")
    if "Friday" not in j["regular_day_tokens"] and "MondayToFriday" not in j["regular_day_tokens"]:
        raise FixtureError("Trip is not Friday-eligible")
    return j

def seconds(s):
    parts=s.split(":")
    if len(parts)!=3 or not all(x.isdigit() for x in parts):raise FixtureError("Invalid departure")
    h,m,sec=map(int,parts)
    if h>99 or m>59 or sec>59:raise FixtureError("Invalid departure values")
    return h*3600+m*60+sec

def local_datetime(f,offset_seconds):
    day=date.fromisoformat(f["service_date"])
    local_midnight=datetime.combine(day,time.min,ZoneInfo(f["time_zone"]))
    # Arithmetic MUST take place on UTC timeline (DST clocks can repeat or skip).
    start=local_midnight.astimezone(timezone.utc)
    return (start+timedelta(seconds=seconds(f["journey"]["published_departure_time"])+offset_seconds)).astimezone(ZoneInfo(f["time_zone"]))

def plan_direct(f,origin_ref,dest_ref,depart_after):
    """Return typed failure, or precisely one direct single-trip candidate."""
    j=validate(f)
    if depart_after.tzinfo is None:raise FixtureError("Request must be timezone-aware")
    origin_indexes=[i for i,s in enumerate(j["stops"]) if s["stop_ref"]==origin_ref and s["activity"] in BOARD]
    dest_indexes=[i for i,s in enumerate(j["stops"]) if s["stop_ref"]==dest_ref and s["activity"] in ALIGHT]
    if not origin_indexes or not dest_indexes:
        return {"outcome":"NO_JOURNEY","reason":"STOP_NOT_BOARDABLE_OR_ALIGHTABLE"}
    for board in origin_indexes:
        for alight in dest_indexes:
            if board>=alight:continue
            b=j["stops"][board];a=j["stops"][alight]
            dep=local_datetime(f,b["departure_offset_seconds"])
            arr=local_datetime(f,a["arrival_offset_seconds"])
            if dep<depart_after:continue
            if arr<=dep:raise FixtureError("Arrival not after departure")
            return {"outcome":"OK","taskType":"JOURNEY","sourceSnapshot":f["source_zip_sha256"],
              "service_date":f["service_date"],
              "trip_occurrence_id":f["operator_noc"]+":"+f["service_code"]+":"+j["journey_code"]+":"+f["service_date"],
              "line":f["line"],"board_stop":b["stop_ref"],"alight_stop":a["stop_ref"],
              "board_name":b["name"],"alight_name":a["name"],
              "departure":dep.isoformat(),"arrival":arr.isoformat(),
              "intermediate_stops":alight-board-1,
              "verification":"OFFLINE_REAL_SOURCE_CANDIDATE_WITH_EXTERNAL_TIMING_ANCHORS_ONLY"}
    return {"outcome":"NO_JOURNEY","reason":"WRONG_DIRECTION_OR_AFTER_DEPARTURE"}
