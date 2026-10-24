"""Auditable day-pattern coverage for both official Coventry 11 revisions; off-host only."""
from collections import Counter,defaultdict
import json
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from inspect_coventry_txc_structure import get,PIN,tag,descendants
from txc_stream import scan
TARGETS=["BODS_PD0001111_813_20260920_32.xml","BODS_PD0001111_813_20261025_33.xml"]
def child(e,n):
    return next((x for x in e if tag(x)==n),None) if e is not None else None
def value(e,n):
    t=child(e,n)
    return (t.text or "").strip() if t is not None else ""
def main():
    raw,_,digest=get()
    if digest!=PIN:raise ValueError("Unexpected archive revision")
    with ZipFile(raw) as z:
        for filename in TARGETS:
            info=z.getinfo(filename)
            if info.file_size>19*1024*1024:raise ValueError("Member too large")
            with z.open(info) as f:scan(f,limit=19*1024*1024)
            with z.open(info) as f:root=ET.parse(f).getroot()
            svc=descendants(root,"Service")[0]
            day_counts=Counter();profile_paths=Counter();dead=0;journeys=descendants(root,"VehicleJourney")
            for v in journeys:
                p=child(v,"OperatingProfile")
                if p is None:p=child(svc,"OperatingProfile")
                r=child(p,"RegularDayType")
                d=child(r,"DaysOfWeek")
                tokens=tuple(tag(x) for x in d) if d is not None else ("MISSING",)
                day_counts["+".join(tokens)]+=1
                if child(v,"StartDeadRun") is not None:dead+=1
                for name in ["SpecialDaysOperation","BankHolidayOperation","OperatingPeriod"]:
                    if child(p,name) is not None:profile_paths[name]+=1
            print(json.dumps({"member":filename,"start":value(child(svc,"OperatingPeriod"),"StartDate"),
                              "end":value(child(svc,"OperatingPeriod"),"EndDate"),
                              "journeys":len(journeys),"regular_day_types":day_counts,
                              "profile_blocks":profile_paths,"with_start_dead_run":dead,
                              "service_code":value(svc,"ServiceCode")},sort_keys=True))
if __name__=="__main__":main()
