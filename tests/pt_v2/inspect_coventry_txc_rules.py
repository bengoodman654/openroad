"""Discover real Coventry 11 timed trip relationships, bounded off-host only."""
from inspect_coventry_txc_structure import get, PIN, TARGET, MAX, tag, descendants, outline
from zipfile import ZipFile
from txc_stream import scan
from collections import Counter
import xml.etree.ElementTree as ET
import json

def one(e,n):
    for c in e:
        if tag(c)==n:return c
    return None
def val(e,n):
    t=one(e,n) if e is not None else None
    return (t.text or "").strip() if t is not None else ""
def profile(p):
    if p is None:return {"day":None,"holiday":[]}
    days=descendants(p,"DaysOfWeek")
    day_nodes=[tag(e) for e in days[0]] if days else []
    return {"days":day_nodes[:8],"special_tags":[tag(e) for e in p.iter() if tag(e) in ("DaysOfOperation","DaysOfNonOperation","SpecialDaysOperation","BankHolidayOperation")],"holiday_tags":[tag(e) for e in descendants(p,"DaysOfNonOperation")[:1][0]] if descendants(p,"DaysOfNonOperation") else []}
def main():
    buf,_,digest=get()
    assert digest==PIN
    with ZipFile(buf) as zipf:
        info=zipf.getinfo(TARGET)
        assert info.file_size<=MAX
        with zipf.open(info) as st:scan(st,limit=MAX)
        with zipf.open(info) as st:root=ET.parse(st).getroot()
    journeys=descendants(root,"VehicleJourney")
    jps={e.get("id"):e for e in descendants(root,"JourneyPattern")}
    sections={e.get("id"):e for e in descendants(root,"JourneyPatternSection")}
    v=journeys[0]
    vid=val(v,"VehicleJourneyCode")
    jp=jps[val(v,"JourneyPatternRef")]
    refs=[(e.text or "").strip() for e in jp if tag(e)=="JourneyPatternSectionRefs"]
    links=[c for ref in refs for c in sections[ref] if tag(c)=="JourneyPatternTimingLink"]
    vl=[c for c in v if tag(c)=="VehicleJourneyTimingLink"]
    sample={
      "service":val(descendants(root,"Service")[0],"ServiceCode"),
      "source_journey_code":vid,"departure":val(v,"DepartureTime"),
      "pattern":val(v,"JourneyPatternRef"),"pattern_refs":refs,
      "pattern_link_count":len(links),"vehicle_link_count":len(vl),
      "pattern_first_links":[outline(x,3) for x in links[:2]],
      "vehicle_first_links":[outline(x,4) for x in vl[:2]],
      "vehicle_first_day_profile":profile(one(v,"OperatingProfile")),
      "first_stop_reference":val(one(links[0],"From"),"StopPointRef") if links else "",
      "first_ten_journeys":[{
         "code":val(x,"VehicleJourneyCode"),"depart":val(x,"DepartureTime"),
         "jp":val(x,"JourneyPatternRef"),"day":profile(one(x,"OperatingProfile"))["days"],
         "vlinks":len([c for c in x if tag(c)=="VehicleJourneyTimingLink"]),
         "dead_run":bool(one(x,"StartDeadRun") is not None or one(x,"EndDeadRun") is not None)
      } for x in journeys[:10]],
      "missing_section_refs":len([k for k in refs if k not in sections]),
      "status":"STRUCTURAL_DISCOVERY_ONLY"
    }
    print(json.dumps(sample,indent=2)[:22000])
if __name__=="__main__":main()
