"""One-off *read-only* bounded structural discovery of verified Coventry service 11 TXC XML.

Not a parser or journey planner. No production service access. No credentials.
"""
import json
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from txc_stream import scan
from inspect_txc_20442 import get
from collections import Counter

PIN="5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0"
TARGET="BODS_PD0001111_813_20260920_32.xml"
MAX=18*1024*1024

def tag(e):return e.tag.rsplit("}",1)[-1]
def descendants(e,k):return [x for x in e.iter() if tag(x)==k]
def path_values(e,fields,limit=3):
    return {k:[(v.text or "").strip()[:90] for v in descendants(e,k)[:limit]] for k in fields}
def outline(e,depth=2,max_children=12):
    if depth<0:return None
    kids=list(e)
    counts=Counter(tag(k) for k in kids)
    output={"tag":tag(e),"attributes":{str(k):str(v)[:80] for k,v in list(e.attrib.items())[:4]},"children":dict(counts)}
    if depth and kids:
        used=set();children=[]
        for c in kids:
            if tag(c) not in used and len(children)<max_children:
                used.add(tag(c))
                children.append(outline(c,depth-1,max_children))
        output["examples"]=children
    elif not kids:output["text"]=(e.text or "").strip()[:80]
    return output

def main():
    blob,size,digest=get()
    assert digest==PIN
    with ZipFile(blob) as z:
        info=z.getinfo(TARGET)
        if info.file_size>MAX:raise ValueError("Target member exceeds safe bounded read")
        with z.open(info) as stream:scan(stream,limit=MAX)  # rejects DTD / external entity
        with z.open(info) as stream:
            tree=ET.parse(stream)
    root=tree.getroot()
    wanted=["Services","Service","Lines","Line","StandardService","JourneyPattern","JourneyPatternSection","JourneyPatternTimingLink","Routes","Route","RouteSection","RouteLink","StopPoints","AnnotatedStopPointRef","StopPoint","VehicleJourneys","VehicleJourney","OperatingProfile","OperatingPeriod"]
    structure={}
    for name in wanted:
        arr=descendants(root,name)
        if arr:structure[name]={"count":len(arr),"first":outline(arr[0],2 if name in ("Service","JourneyPattern","JourneyPatternTimingLink","VehicleJourney","OperatingProfile","AnnotatedStopPointRef","RouteLink") else 1)}
    samples={}
    for name,fields in {
        "VehicleJourney":["VehicleJourneyCode","JourneyPatternRef","LineRef","ServiceRef","DepartureTime","VehicleJourneyTimingLink","OperatingProfile"],
        "JourneyPattern":["JourneyPatternSectionRefs","JourneyPatternSectionRef","RouteRef","Direction","OperatingProfile"],
        "JourneyPatternTimingLink":["From","To","RunTime","WaitTime"],
        "AnnotatedStopPointRef":["StopPointRef","CommonName","LocalityName","Location"],
        "Service":["ServiceCode","OperatingPeriod","RegularDayType","DaysOfWeek"]
    }.items():
        arr=descendants(root,name)
        if arr:samples[name]=[path_values(e,fields,2) for e in arr[:2]]
    print(json.dumps({"target":TARGET,"member_bytes":info.file_size,"root":tag(root),"structure":structure,"samples":samples,"status":"STRUCTURE_ONLY_NOT_TIMETABLE_VALIDATION"},indent=1)[:39000])
if __name__=="__main__":main()
