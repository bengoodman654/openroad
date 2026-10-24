"""Extract one bounded, *real-source* Coventry 11 Saturday timetable fixture.

Uses an operator-published TXC member pinned by parent ZIP SHA. Converts explicit
journey-pattern and vehicle-journey references to a small provenance-labelled JSON
fixture. Timings are computed CANDIDATES, not independently validated departures;
nothing is installed to the live server and no production acceptance is claimed.
"""
from datetime import date
import json
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from inspect_coventry_txc_structure import get, PIN, TARGET, MAX, tag, descendants
from txc_stream import scan

SERVICE_DAY=date(2026,10,24)
DATE="2026-10-24"
DAY="Saturday"
MINS={"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"}

def direct(e,n):
    return next((c for c in e if tag(c)==n),None) if e is not None else None
def value(e,n):
    c=direct(e,n)
    return (c.text or "").strip() if c is not None else ""
def duration(s):
    m=re.fullmatch(r'P(?:0D|(?:(\d+)D))?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?',s or "")
    if m is None:raise ValueError("Unsupported TXC duration: "+repr(s))
    return int(m[1] or 0)*86400+int(m[2] or 0)*3600+int(m[3] or 0)*60+round(float(m[4] or 0))
def clock(s):
    m=re.fullmatch(r'(\d{2}):([0-5]\d):([0-5]\d)',s)
    if not m:raise ValueError("Invalid departure time")
    return int(m[1])*3600+int(m[2])*60+int(m[3])
def at(s):
    return f"{s//86400:+d}d {s%86400//3600:02}:{s%3600//60:02}:{s%60:02}"

def day_rule(prof):
    """Strictly support explicit day groups, never assume holidays/schools."""
    if prof is None:return None
    regular=direct(prof,"RegularDayType")
    days=direct(regular,"DaysOfWeek")
    if days is None:return None
    tokens={tag(e) for e in days}
    active=("Saturday" in tokens or "MondayToSaturday" in tokens or "MondayToSunday" in tokens or "Weekend" in tokens)
    # SpecialDaysOperation and BankHoliday DaysOfOperation require a fuller calendar.
    if direct(prof,"SpecialDaysOperation") is not None:return None
    bank=direct(prof,"BankHolidayOperation")
    if direct(bank,"DaysOfOperation") is not None:return None
    return active

def load():
    raw,raw_size,digest=get()
    if digest!=PIN:raise ValueError("Coventry dataset changed; quarantine")
    with ZipFile(raw) as z:
        info=z.getinfo(TARGET)
        if info.file_size>MAX:raise ValueError("TXC member over size cap")
        with z.open(info) as src:scan(src,limit=MAX)
        with z.open(info) as src:root=ET.parse(src).getroot()
    return root,info,raw_size,digest

def candidate(root):
    service=descendants(root,"Service")[0]
    reg=value(service,"RegisteredOperatorRef")
    code=value(service,"ServiceCode")
    line=next((value(x,"LineName") for x in descendants(service,"Line")),None)
    start=value(direct(service,"OperatingPeriod"),"StartDate")
    if (reg,code,line)!=("TCVW","PD0001111:813","11") or not (start<=DATE):
        raise ValueError("Wrong service identity or source date")
    stop_index={}
    for s in descendants(root,"AnnotatedStopPointRef"):
        k=value(s,"StopPointRef")
        if k:stop_index[k]={"name":value(s,"CommonName"),"locality":value(s,"LocalityName")}
    patterns={e.get("id"):e for e in descendants(service,"JourneyPattern")}
    sections={e.get("id"):e for e in descendants(root,"JourneyPatternSection")}
    choices=[];reasons={}
    for v in descendants(root,"VehicleJourney"):
        if value(v,"ServiceRef")!=code or value(v,"LineRef")!="TCVW:PD0001111:813:11":continue
        prof=direct(v,"OperatingProfile")
        if prof is None:prof=direct(service,"OperatingProfile")
        allowed=day_rule(prof)
        if allowed is not True:
            reasons["non_saturday_or_unsupported_calendar"]=reasons.get("non_saturday_or_unsupported_calendar",0)+1
            continue
        if direct(v,"StartDeadRun") is not None or direct(v,"EndDeadRun") is not None:
            reasons["dead_run_or_short_working"]=reasons.get("dead_run_or_short_working",0)+1
            continue
        if direct(v,"Frequency") is not None:
            reasons["frequency"]=reasons.get("frequency",0)+1
            continue
        pattern=patterns.get(value(v,"JourneyPatternRef"))
        if pattern is None:continue
        refs=[(e.text or "").strip() for e in pattern if tag(e)=="JourneyPatternSectionRefs"]
        if not refs or any(r not in sections for r in refs):continue
        links=[e for r in refs for e in sections[r] if tag(e)=="JourneyPatternTimingLink"]
        if not links:continue
        overrides={}
        for e in v:
            if tag(e)=="VehicleJourneyTimingLink":
                ref=value(e,"JourneyPatternTimingLinkRef")
                if ref in overrides:raise ValueError("Duplicated vehicle override link")
                overrides[ref]=e
        if set(overrides)-{l.get("id") for l in links}:continue
        try:
            raw_start=clock(value(v,"DepartureTime"))
            stops=[];current=raw_start;prev=None
            for i,link in enumerate(links):
                a=direct(link,"From");b=direct(link,"To")
                source=value(a,"StopPointRef");dest=value(b,"StopPointRef")
                if not source or not dest or (prev is not None and prev!=source):
                    raise ValueError("Discontinuous journey pattern")
                override=overrides.get(link.get("id"))
                run=value(override,"RunTime") or value(link,"RunTime")
                if not run:raise ValueError("Missing runtime")
                sec=duration(run)
                # WaitTime at From must be treated separately from travel time.
                ow=direct(override,"From") if override is not None else None
                lw=value(ow,"WaitTime") or value(a,"WaitTime")
                wait=duration(lw) if lw else 0
                if i==0:
                    stops.append({"stop_ref":source,**stop_index.get(source,{}),
                                  "arrival_offset_seconds":0,"departure_offset_seconds":0})
                stops[-1]["departure_offset_seconds"]=current+wait-raw_start
                depart=current+wait
                arrive=depart+sec
                stops.append({"stop_ref":dest,**stop_index.get(dest,{}),
                              "arrival_offset_seconds":arrive-raw_start,
                              "departure_offset_seconds":arrive-raw_start})
                current=arrive
                prev=dest
            if len(stops)<8 or len(stops)>150 or any(not x.get("name") for x in stops):
                raise ValueError("Missing stops or unsuitable length")
            choices.append({
              "journey_code":value(v,"VehicleJourneyCode"),"pattern":value(v,"JourneyPatternRef"),
              "direction":value(pattern,"Direction"),"destination":value(pattern,"DestinationDisplay"),
              "published_departure_time":value(v,"DepartureTime"),
              "regular_day_tokens":[tag(x) for x in direct(direct(prof,"RegularDayType"),"DaysOfWeek")],
              "bank_holiday_exclusions":[tag(x) for x in descendants(prof,"DaysOfNonOperation")[0]] if descendants(prof,"DaysOfNonOperation") else [],
              "stop_count":len(stops),"stops":stops,
              "timing_semantics":"derived stop offsets from TXC RunTime and From/WaitTime; unverified by independent published stop timetable",
              "unhandled_special_rules":False
            })
        except ValueError as exc:
            name=str(exc)[:70]
            reasons[name]=reasons.get(name,0)+1
            continue
    return service,choices,reasons

def main():
    root,info,size,digest=load()
    _,choices,reasons=candidate(root)
    print("SOURCE_SELECTION_DIAGNOSTIC "+json.dumps({"candidate_count":len(choices),"reasons":reasons},sort_keys=True))
    if not choices:raise ValueError("No clean Saturday Coventry 11 reference trip found; do not invent fixture")
    # Select a modest, source-complete pattern and stable ID; no clock-time guessing.
    choices.sort(key=lambda t:(t["stop_count"],t["published_departure_time"],t["journey_code"]))
    chosen=choices[0]
    result={
       "kind":"REAL_TXC_SOURCE_CANDIDATE_TIMETABLE_NOT_INDEPENDENTLY_VERIFIED",
       "operator_noc":"TCVW","service_code":"PD0001111:813","line":"11",
       "source_dataset":"20442","source_zip_sha256":digest,"source_xml_member":TARGET,
       "service_date":DATE,"weekday":"Saturday","time_zone":"Europe/London",
       "calendar_assumptions":["2026-10-24 normal Saturday; government list has no public bank holiday","TXC vehicle journey RegularDayType matches Saturday","special exception calendars beyond normal and BankHoliday exclusions require fuller engine"],
       "candidate_count":len(choices),"skipped":reasons,
       "journey":chosen,
       "production_acceptance_cases_passed":0
    }
    print("FIXTURE_JSON_START")
    print(json.dumps(result,separators=(",",":")))
    print("FIXTURE_JSON_END")
if __name__=="__main__":main()
