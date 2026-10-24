"""Exercise real Coventry day snapshots through multi-trip direct-route prototype.

One bounded BODS ZIP download and two selected XML members on disposable runner.
No production writes. The Sunday DST transition is explicitly unsupported by
the direct-route prototype, even though its service candidates can be listed.
"""
from collections import Counter
from datetime import date,datetime,time
from zoneinfo import ZoneInfo
from zipfile import ZipFile
import json
from inspect_coventry_txc_structure import get,PIN
from coventry_11_multitrip import FILES,tree_for,extract_trips,revision
from multitrip_direct import direct_options

def build(d,roots):
    file=revision(d)
    day=extract_trips(roots[file],d)
    trips,rejected=day
    return {"kind":"REAL_TXC_MULTITRIP_OFFLINE_CANDIDATES","operator_noc":"TCVW",
            "service_code":"PD0001111:813","line":"11","source_dataset":"20442",
            "source_zip_sha256":PIN,"source_xml_member":file,
            "service_date":d.isoformat(),"time_zone":"Europe/London","trips":trips},rejected

def first_valid_pair(journeys):
    for journey in journeys:
        stops=journey["stops"]
        board=next((s for s in stops[:-1] if s["activity"] in ("pickUp","pickUpAndSetDown")),None)
        exit=next((s for s in reversed(stops) if s["activity"] in ("setDown","pickUpAndSetDown")),None)
        if board is not None and exit is not None and board!=exit:
            return board["stop_ref"],exit["stop_ref"]
    raise ValueError("No usable passenger stop pair")

def main():
    zipped,_,sha=get()
    if sha!=PIN:raise ValueError("Published source changed: quarantine")
    with ZipFile(zipped) as zipf:
        roots={v:tree_for(zipf,v) for v in FILES.values()}
    audits=[]
    for d in [date(2026,10,23),date(2026,10,24),date(2026,10,25),date(2026,10,26)]:
        data,excluded=build(d,roots)
        origin,destination=first_valid_pair(data["trips"])
        q=datetime.combine(d,time.min,ZoneInfo("Europe/London"))
        result=direct_options(data,origin,destination,q)
        if d.isoformat()=="2026-10-25":
            if result["outcome"]!="UNSUPPORTED_CALENDAR_TIME_TRANSITION":raise ValueError("DST fail-closed contract breached")
        else:
            if result["outcome"]!="OK":raise ValueError(f"Could not route known {d} real-service stop pair: {result}")
            if not 1<=len(result["results"])<=3:raise ValueError("Result limit breached")
            if any(c["source_snapshot"]!=PIN for c in result["results"]):
                raise ValueError("Snapshot mix")
            if len(set(x["trip_occurrence_id"] for x in result["results"]))!=len(result["results"]):
                raise ValueError("Duplicate displayed itinerary")
        audits.append({"date":d.isoformat(),"published_trip_candidates":len(data["trips"]),
                       "origin_stop":origin,"destination_stop":destination,
                       "outcome":result["outcome"],"displayed_options":len(result.get("results",[])),
                       "option_examples":result.get("results",[])[:2],
                       "excluded":excluded})
    print(json.dumps({
        "kind":"OFFHOST_REAL_SOURCE_MULTI_TRIP_ROUTING_PILOT_NOT_PRODUCTION_ACCEPTANCE",
        "source_dataset":"20442","sha256":PIN,
        "cases":audits,"production_acceptance_cases_passed":0
    },sort_keys=True))
if __name__=="__main__":main()
