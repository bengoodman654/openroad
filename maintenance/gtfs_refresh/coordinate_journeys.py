"""Source-pinned, scheduled-only coordinate-to-coordinate regional planner.

Combines the tested city connection-scan and up-to-two-bus transfers with
explicit lower bounds on endpoint access walks. For real turn-by-turn guidance
the endpoints still need connected, proven pedestrian geometry, so no
result returned here is selectable or considered accessibility-certified.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

from pilot.gtfs_engine import distance_m
from pilot.journey_options import Footpath, journey_options


def coordinate_journeys(snapshot, origin, destination, earliest_sec,
                        max_walk_m=800, max_nearby=5, max_pairs=25,
                        max_results=3, transfer_bundle=None, cancel=None,
                        budget_s=10.0):
    if (max_walk_m < 50 or max_walk_m > 2500 or
        max_nearby < 1 or max_nearby > 12 or
        max_pairs < 1 or max_pairs > 100 or
        max_results < 1 or max_results > 5 or
        budget_s <= 0 or budget_s > 30 or
        earliest_sec < 0 or earliest_sec > 172800):
        raise ValueError("Unsupported regional journey search settings")
    started=time.monotonic()
    def cancelled():
        return bool(cancel and cancel())
    def time_expired():
        return time.monotonic()-started > budget_s
    if cancelled():
        return {"outcome":"CANCELLED","results":[],"researchOnly":True}
    if transfer_bundle is None:
        links=()
    else:
        if (not isinstance(transfer_bundle,dict) or
            transfer_bundle.get("outcome")!="OK" or
            transfer_bundle.get("researchOnly") is not True or
            transfer_bundle.get("selectable") is not False or
            transfer_bundle.get("gtfsSourceSha256")!=snapshot.source_sha256 or
            not transfer_bundle.get("graphSourceSha256")):
            raise ValueError("Walking transfer certificate mismatches timetable")
        links=transfer_bundle.get("links")
        if not isinstance(links,list) or len(links)>2000:
            raise ValueError("Unbounded walking review certificate")
        for w in links:
            if (not isinstance(w,Footpath) or not w.verified or
                w.source_sha256!=transfer_bundle["graphSourceSha256"] or
                w.provider!="OpenStreetMap" or
                w.metres<=0 or not w.geometry):
                raise ValueError("Uncertified pedestrian interchange")
    def candidates(point):
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in point):
            raise ValueError("Invalid origin or destination")
        raw=[]
        for i,stop in enumerate(snapshot.stops.values()):
            if i%128==0:
                if cancelled():return None
                if time_expired():return "budget"
            d=distance_m(point,(stop.lat,stop.lon))
            if d<=max_walk_m:
                raw.append((d,stop.id))
        raw.sort(key=lambda x:(x[0],x[1]))
        return raw
    origin_candidates=candidates(origin)
    destination_candidates=candidates(destination)
    if origin_candidates is None or destination_candidates is None:
        return {"outcome":"CANCELLED","results":[],"researchOnly":True}
    if origin_candidates=="budget" or destination_candidates=="budget":
        return {"outcome":"SEARCH_LIMIT","reasonCode":"TIME_BUDGET",
                "results":[],"researchOnly":True}
    if not origin_candidates or not destination_candidates:
        return {"outcome":"COVERAGE_MISSING",
                "reasonCode":"NO_STOP_WITHIN_USER_WALK_LIMIT",
                "results":[],"researchOnly":True}
    # The nearest-stop shortlist is a performance cap, not evidence
    # that a city has no other valid service. Report incomplete searches.
    incomplete=(len(origin_candidates)>max_nearby or
                len(destination_candidates)>max_nearby)
    pairs=[]
    for access,a in origin_candidates[:max_nearby]:
        for egress,b in destination_candidates[:max_nearby]:
            if a != b and access+egress<=max_walk_m:
                pairs.append((access+egress,access,egress,a,b))
    pairs.sort(key=lambda x:(x[0],x[3],x[4]))
    incomplete=incomplete or len(pairs)>max_pairs
    results=[]
    if not pairs:
        return {"outcome":"SEARCH_LIMIT" if incomplete else "NO_JOURNEY",
                "reasonCode":"STOP_CANDIDATE_CAP" if incomplete else
                  "ACCESS_EGRESS_LOWER_BOUNDS_EXCEED_WALK_LIMIT",
                "results":[],"researchOnly":True}
    for _,access,egress,board_stop,last_stop in pairs[:max_pairs]:
        if cancelled():
            return {"outcome":"CANCELLED","results":[],"researchOnly":True}
        if time_expired():
            incomplete=True
            break
        remaining=max_walk_m-math.ceil(access)-math.ceil(egress)
        if remaining<0:continue
        result=journey_options(
            snapshot,board_stop,last_stop,
            earliest_sec+math.ceil(access/1.25),
            footpaths=links,max_walk_m=remaining,
            max_transfers=2,max_horizon_sec=7200,
            max_results=3,max_labels=45000,
            # Both explicit cancellation and request deadline must stop
            # a long-running connection scan, not only the next stop pair.
            cancel_check=lambda: cancelled() or time_expired())
        if result.get("outcome")=="CANCELLED":
            if cancelled():
                return {"outcome":"CANCELLED","results":[],"researchOnly":True}
            incomplete=True
            break
        if result.get("outcome")=="SEARCH_LIMIT":
            incomplete=True
            continue
        if result.get("outcome")!="OK":continue
        for option in result.get("results",[]):
            legs=option.get("legs",[])
            buses=[step for step in legs if step.get("mode")=="BUS"]
            if not buses:continue
            walked_between=int(option.get("walkedMetres",0))
            if access+egress+walked_between>max_walk_m:
                continue
            canonical={
                "source":snapshot.source_sha256,
                "date":snapshot.service_day.isoformat(),
                "boardingStop":board_stop,"alightingStop":last_stop,
                "busSteps":[[s["tripOccurrence"],s["from"],s["to"],
                             s["depart"],s["arrive"]] for s in buses],
                "walkSteps":[[s["from"],s["to"],s["metres"]]
                             for s in legs if s.get("mode")=="WALK"],
            }
            journey_id=hashlib.sha256(
                json.dumps(canonical,sort_keys=True,
                           separators=(",",":")).encode()).hexdigest()[:20]
            results.append({
                "clearRouteId":journey_id,
                "boardingStop":board_stop,
                "alightingStop":last_stop,
                "departureSec":buses[0]["depart"],
                "arrivalLowerBoundSec":option["arrival"]+
                    math.ceil(egress/1.25),
                "busLegs":buses,
                "transferWalkingLegs":[s for s in legs
                                       if s.get("mode")=="WALK"],
                "changes":option.get("transfers",0),
                "accessWalkMetresLowerBound":round(access),
                "egressWalkMetresLowerBound":round(egress),
                "reviewedTransferWalkMetres":walked_between,
                "walkingDistanceMetresLowerBound":
                    math.ceil(access+egress)+walked_between,
                "sourceArchiveSha256":snapshot.source_sha256,
                "researchOnly":True,"selectable":False,
                "accessWalkGeometryVerified":False,
                "egressWalkGeometryVerified":False,
                "accessibilityVerified":False,
                "warnings":sorted(set(option["warnings"]+[
                    "UNVERIFIED_ORIGIN_DESTINATION_PEDESTRIAN_ACCESS"])),
            })
    if cancelled():
        return {"outcome":"CANCELLED","results":[],"researchOnly":True}
    results.sort(key=lambda o:(o["arrivalLowerBoundSec"],
                               o["changes"],
                               o["walkingDistanceMetresLowerBound"],
                               o["clearRouteId"]))
    distinct=[]
    sequences=set()
    for option in results:
        # Discard duplicate departures from slightly different nearby
        # stops when the underlying actual buses/ride sections coincide.
        sequence=tuple((s["tripOccurrence"],s["depart"],s["arrive"])
                       for s in option["busLegs"])
        if sequence in sequences:continue
        sequences.add(sequence)
        distinct.append(option)
        if len(distinct)>=max_results:break
    outcome="OK" if distinct else ("SEARCH_LIMIT" if incomplete else "NO_JOURNEY")
    return {
        "outcome":outcome,"researchOnly":True,
        "snapshotId":snapshot.source_sha256,
        "incompleteSearch":incomplete,
        "reasonCode":("INCOMPLETE_PAIR_SEARCH" if incomplete else
                      "NO_SCHEDULED_STOP_TO_STOP_JOURNEY" if not distinct else
                      "RESEARCH_ONLY_WALK_ACCESS_UNVERIFIED"),
        "results":distinct,
    }
