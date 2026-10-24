"""Read two pinned Coventry-11 TXC source revisions once and audit multiple test dates.

Heavy XML work only on disposable runner; no server request, no production
publish, no fabricated service. Emits summary metadata, not full raw timetables.
"""
import json
from collections import Counter
from datetime import date
from zipfile import ZipFile
from inspect_coventry_txc_structure import get,PIN
from coventry_11_multitrip import FILES,tree_for,extract_trips,revision

def main():
    archive,size,sha=get()
    if sha!=PIN:raise ValueError("Unapproved official source revision")
    with ZipFile(archive) as zipf:
        roots={k:tree_for(zipf,filename) for k,filename in FILES.items()}
    day_summaries=[]
    for d in [date(2026,10,23),date(2026,10,24),date(2026,10,25),date(2026,10,26)]:
        selected=revision(d)
        key=next(k for k,v in FILES.items() if v==selected)
        trips,skipped=extract_trips(roots[key],d)
        directions=Counter(j["direction"] for j in trips)
        hourbins=Counter(j["published_departure_time"][:2] for j in trips)
        dead=sum(j["has_positioning_dead_run"] for j in trips)
        duplicate_groups={}
        for trip in trips:
            signature=(trip["published_departure_time"],trip["direction"],
                       tuple((s["stop_ref"],s["arrival_offset_seconds"],
                              s["departure_offset_seconds"],s["activity"]) for s in trip["stops"]))
            duplicate_groups.setdefault(signature,[]).append(trip["journey_code"])
        duplicated=[v for v in duplicate_groups.values() if len(v)>1]
        identifiers={t["journey_code"] for t in trips}
        sample=next((t for t in trips if t["journey_code"]=="VJ136"),None)
        day_summaries.append({
            "date":d.isoformat(),"weekday":d.strftime("%A"),"selected_member":selected,
            "exact_duplicate_groups":len(duplicated),
            "redundant_candidate_records":sum(len(g)-1 for g in duplicated),
            "duplicate_examples":duplicated[:5],
            "candidates":len(trips),"unique_journey_codes":len(identifiers),
            "directions":dict(directions),"first_departure":min((t["published_departure_time"] for t in trips),default=None),
            "last_departure":max((t["published_departure_time"] for t in trips),default=None),
            "start_dead_runs_retained":dead,"hour_distribution":dict(hourbins),
            "rejected":skipped,
            "golden_vj136":(
                {"first_stop":sample["stops"][0]["stop_ref"],
                 "last_stop":sample["stops"][-1]["stop_ref"],
                 "first_departure":sample["published_departure_time"],
                 "last_arrival_offset_seconds":sample["stops"][-1]["arrival_offset_seconds"],
                 "stop_count":len(sample["stops"])}
                if sample else None
            )
        })
    if not any(x["golden_vj136"] and x["golden_vj136"]["last_arrival_offset_seconds"]==1560
               for x in day_summaries):
        raise ValueError("Regression: known Coventry 11 real timetable stop timings differ")
    if not all(x["candidates"]>0 for x in day_summaries):
        raise ValueError("Day coverage unexpectedly empty; quarantine until diagnosed")
    if not all(x["unique_journey_codes"]==x["candidates"] for x in day_summaries):
        raise ValueError("Duplicate canonical vehicle journey IDs")
    print(json.dumps({
        "kind":"OFFHOST_MULTITRIP_SOURCE_COVERAGE_NOT_PRODUCTION_ACCEPTANCE",
        "dataset":"20442","sha256":sha,"dates":day_summaries,
        "warnings":["25 Oct is UK DST fallback date; service-time semantics require explicit validation",
                    "No independent check of all departures, holiday/day overrides or geometry",
                    "All output is experimental evidence; 0/105 live integration acceptances"],
        "production_acceptance_cases_passed":0
    },sort_keys=True))
if __name__=="__main__":main()
