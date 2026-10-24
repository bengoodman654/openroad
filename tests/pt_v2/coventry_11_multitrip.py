"""Coventry service 11 off-host multi-trip importer prototype.

Only pinned DfT TXC source members and explicitly approved days. Never used for
passenger guidance or production. All errors fail closed; full holiday/school,
accessibility, route-shape and DST semantics are not implemented.
"""
from collections import Counter
from datetime import date
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from inspect_coventry_txc_structure import get,PIN,tag,descendants
from txc_stream import scan

FILES={
    "2026-09-20": "BODS_PD0001111_813_20260920_32.xml",
    "2026-10-25": "BODS_PD0001111_813_20261025_33.xml",
}
# A controlled test scope, not a reusable bank-holiday lookup.
APPROVED_DATES={"2026-10-23","2026-10-24","2026-10-25","2026-10-26","2026-10-27"}
WEEK={"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"}
GROUPS={
    "MondayToFriday":WEEK & {"Monday","Tuesday","Wednesday","Thursday","Friday"},
    "MondayToSaturday":WEEK-{"Sunday"},
    "MondayToSunday":WEEK,
    "SaturdaySunday":{"Saturday","Sunday"},
    "Weekend":{"Saturday","Sunday"},
    "NotSaturday":WEEK-{"Saturday"},
    "NotSunday":WEEK-{"Sunday"},
}
class UnsupportedTXC(ValueError):pass

def child(e,n):
    return next((x for x in e if tag(x)==n),None) if e is not None else None
def value(e,n):
    x=child(e,n)
    return (x.text or "").strip() if x is not None else ""
def seconds(t):
    m=re.fullmatch(r"(\d{2}):([0-5]\d):([0-5]\d)",t or "")
    if not m:raise UnsupportedTXC("Malformed TXC departure")
    return int(m[1])*3600+int(m[2])*60+int(m[3])
def span(s):
    m=re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",s or "")
    if not m:raise UnsupportedTXC("Unsupported TXC runtime")
    result=int(m[1] or 0)*86400+int(m[2] or 0)*3600+int(m[3] or 0)*60+round(float(m[4] or 0))
    if result<0 or result>6*3600:raise UnsupportedTXC("Implausible runtime")
    return result

def revision(on_date):
    d=on_date.isoformat()
    if d not in APPROVED_DATES:raise UnsupportedTXC("Date outside independently scoped test days")
    return FILES["2026-10-25"] if d>="2026-10-25" else FILES["2026-09-20"]

def operating_day(profile,on_date,non_bank_holiday_known=False):
    """Return True/False/None. None = unsupported / unknown, never silently valid."""
    if profile is None:return None
    regular=child(profile,"RegularDayType")
    weekdays=child(regular,"DaysOfWeek")
    if weekdays is None:return None
    tokens={tag(e) for e in weekdays}
    if not tokens or tokens-(WEEK|set(GROUPS)):return None
    days=set()
    for t in tokens:days.update(GROUPS.get(t,{t}))
    if on_date.strftime("%A") not in days:return False
    # A profile's bank-holiday exclusions do NOT invalidate an ordinary weekday.
    bank=child(profile,"BankHolidayOperation")
    if bank is not None and not non_bank_holiday_known:return None
    # No implicit school-day / custom-date / special-period assumptions.
    if child(profile,"SpecialDaysOperation") is not None:return None
    if child(profile,"ServicedOrganisationDayType") is not None:return None
    return True

def tree_for(z,filename):
    info=z.getinfo(filename)
    if info.file_size>20*1024*1024:raise UnsupportedTXC("XML over import per-file limit")
    with z.open(info) as st:scan(st,limit=20*1024*1024)
    with z.open(info) as st:
        # DTD prohibited by successful expat scan above. Stream-safe selected member.
        return ET.parse(st).getroot()

def extract_trips(root,on_date):
    source=descendants(root,"Service")
    if len(source)!=1:raise UnsupportedTXC("Unexpected service scope")
    svc=source[0]
    if (value(svc,"RegisteredOperatorRef"),value(svc,"ServiceCode"))!=("TCVW","PD0001111:813"):
        raise UnsupportedTXC("Wrong operator or service")
    lines=descendants(svc,"Line")
    if len(lines)!=1 or value(lines[0],"LineName")!="11":raise UnsupportedTXC("Wrong line")
    period=child(svc,"OperatingPeriod")
    if on_date.isoformat()<value(period,"StartDate"):raise UnsupportedTXC("Before source revision start")
    end=value(period,"EndDate")
    if end and on_date.isoformat()>end:raise UnsupportedTXC("After source revision end")
    stops={}
    for stop in descendants(root,"AnnotatedStopPointRef"):
        ref=value(stop,"StopPointRef")
        if ref:stops[ref]={"stop_ref":ref,"name":value(stop,"CommonName"),"locality":value(stop,"LocalityName")}
    patterns={x.get("id"):x for x in descendants(svc,"JourneyPattern")}
    sections={x.get("id"):x for x in descendants(root,"JourneyPatternSection")}
    accepted=[];rejected=Counter()
    for v in descendants(root,"VehicleJourney"):
        if value(v,"ServiceRef")!="PD0001111:813" or value(v,"LineRef")!="TCVW:PD0001111:813:11":
            rejected["foreign_line"]+=1;continue
        p=child(v,"OperatingProfile")
        if p is None:p=child(svc,"OperatingProfile")
        day=operating_day(p,on_date,non_bank_holiday_known=True)
        if day is False:rejected["not_running_on_day"]+=1;continue
        if day is None:rejected["unsupported_calendar"]+=1;continue
        if child(v,"Frequency") is not None:
            rejected["unsupported_frequency"]+=1;continue
        jp=patterns.get(value(v,"JourneyPatternRef"))
        if jp is None:rejected["missing_pattern"]+=1;continue
        sectionrefs=[(x.text or "").strip() for x in jp if tag(x)=="JourneyPatternSectionRefs"]
        if not sectionrefs or any(x not in sections for x in sectionrefs):
            rejected["missing_sections"]+=1;continue
        links=[x for s in sectionrefs for x in sections[s] if tag(x)=="JourneyPatternTimingLink"]
        overrides={}
        for x in v:
            if tag(x)=="VehicleJourneyTimingLink":
                ref=value(x,"JourneyPatternTimingLinkRef")
                if ref in overrides:raise UnsupportedTXC("Duplicate override in source")
                overrides[ref]=x
        if set(overrides)-{x.get("id") for x in links}:
            rejected["unresolved_override"]+=1;continue
        try:
            if not links:raise UnsupportedTXC("No links")
            start=seconds(value(v,"DepartureTime"))
            now=start
            result=[];previous=None
            for i,link in enumerate(links):
                frm=child(link,"From");to=child(link,"To")
                a=value(frm,"StopPointRef");b=value(to,"StopPointRef")
                if not a or not b or (previous and previous!=a):raise UnsupportedTXC("Discontinuous pattern")
                if a not in stops or b not in stops or not stops[a]["name"] or not stops[b]["name"]:
                    raise UnsupportedTXC("Missing annotated stop")
                override=overrides.get(link.get("id"))
                runtime=value(override,"RunTime") or value(link,"RunTime")
                waitfrom=child(override,"From")
                waiting=value(waitfrom,"WaitTime") or value(frm,"WaitTime")
                travel=span(runtime)
                wait=span(waiting) if waiting else 0
                activityfrom=value(waitfrom,"Activity") or value(frm,"Activity")
                activityto=value(child(override,"To"),"Activity") or value(to,"Activity")
                if i==0:
                    result.append({**stops[a],"arrival_offset_seconds":0,"departure_offset_seconds":0,
                                   "activity":activityfrom})
                now+=wait
                result[-1]["departure_offset_seconds"]=now-start
                now+=travel
                result.append({**stops[b],"arrival_offset_seconds":now-start,"departure_offset_seconds":now-start,
                               "activity":activityto})
                previous=b
            if not 2<=len(result)<=150:raise UnsupportedTXC("Invalid stop length")
            if any(s["activity"] not in ("pickUp","setDown","pickUpAndSetDown","pass") for s in result):
                raise UnsupportedTXC("Unsupported stop activity")
            # StartDeadRun is depot positioning, NOT disqualification of the public journey.
            accepted.append({
                "journey_code":value(v,"VehicleJourneyCode"),
                "pattern":value(v,"JourneyPatternRef"),
                "direction":value(jp,"Direction"),
                "destination":value(jp,"DestinationDisplay"),
                "published_departure_time":value(v,"DepartureTime"),
                "has_positioning_dead_run":child(v,"StartDeadRun") is not None,
                "stops":result,
            })
        except (UnsupportedTXC,ValueError) as exc:
            rejected[str(exc)[:55]]+=1
    codes=[t["journey_code"] for t in accepted]
    if len(set(codes))!=len(codes):raise UnsupportedTXC("Ambiguous duplicate journey codes")
    return sorted(accepted,key=lambda t:(t["published_departure_time"],t["journey_code"])),dict(rejected)

def load_day(on_date):
    filename=revision(on_date)
    zdata,size,digest=get()
    if digest!=PIN:raise UnsupportedTXC("Archive SHA changed")
    with ZipFile(zdata) as z:root=tree_for(z,filename)
    trips,rejections=extract_trips(root,on_date)
    return {"kind":"REAL_TXC_MULTITRIP_OFFLINE_CANDIDATES",
            "operator_noc":"TCVW","line":"11","service_code":"PD0001111:813",
            "source_dataset":"20442","source_zip_sha256":digest,
            "source_xml_member":filename,"service_date":on_date.isoformat(),
            "time_zone":"Europe/London","service_day_weekday":on_date.strftime("%A"),
            "calendar_scope":"approved ordinary non-bank-holiday service days only; not school/special calendars or DST arithmetic validated",
            "trips":trips,"rejected":rejections,"production_acceptance_cases_passed":0}
# Import at the bottom to allow purely synthetic model testing offline.
from inspect_coventry_txc_structure import get,PIN
