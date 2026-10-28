"""Reproducible OFF-HOST real-OSM reconnaissance for Bristol/Coventry.

A mapped bus-stop tag and nearby graph node are NOT a verified GTFS stop
connector. Results are diagnostic; NEVER use them as live journey options.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import json

from pilot.gtfs_engine import CENTRES, Stop, distance_m
from pilot.pedestrian_graph import (
    load_osm_pbf_offhost, propose_stop_anchors
)


@dataclass
class StopSnapshot:
    stops: dict[str, Stop]


def audit_city(city: str, path: str, radius_m: int = 2500,
               pair_limit: int = 40) -> dict:
    centre=CENTRES[city]
    graph=load_osm_pbf_offhost(path,centre=centre,radius_m=radius_m)
    if not graph.nodes or graph.accepted_ways < 10:
        raise ValueError(f"{city}: REAL_OSM_COVERAGE_MISSING")
    osm_stops={}
    for item in graph.transit_stops.values():
        key="osm:"+item["osmNode"]
        osm_stops[key]=Stop(key,item["name"],item["lat"],item["lon"])
    candidate_snapshot=StopSnapshot(osm_stops)
    suggestions=propose_stop_anchors(
        graph,candidate_snapshot,max_snap_m=40,max_candidates=3)
    by_stop={}
    for candidate in suggestions:
        by_stop.setdefault(candidate.stop_id,[]).append(candidate)
    # These trials deliberately operate on UNVERIFIED OSM stop-node
    # suggestions. They only test mapped topology, NOT traversable bus-stop
    # access, GTFS stop IDs, accessible crossings or usable itineraries.
    trials=0
    connected=0
    rejected=0
    samples=[]
    keys=sorted(by_stop)
    for origin in keys:
        if trials >= pair_limit:
            break
        s=osm_stops[origin]
        near=[]
        for dest in keys:
            if dest==origin:
                continue
            t=osm_stops[dest]
            d=distance_m((s.lat,s.lon),(t.lat,t.lon))
            if 20 <= d <= 300:
                near.append((d,dest))
        if not near:
            continue
        _,target=min(near)
        a=by_stop[origin][0].node_id
        b=by_stop[target][0].node_id
        path_result=graph.route(a,b,max_walk_m=600)
        trials+=1
        if path_result:
            connected+=1
            if len(samples)<5:
                samples.append({"from":origin,"to":target,
                                "walkMetres":path_result.metres,
                                "pathNodes":len(path_result.node_ids),
                                "mappedGeometryOnly":
                                path_result.mapped_foot_geometry})
        else:
            rejected+=1
    return {
        "city":city,
        "status":"RESEARCH_ONLY_UNVERIFIED_STOP_ACCESS",
        "centre":list(centre),"radiusM":radius_m,
        "source":"OpenStreetMap via Geofabrik",
        "sourceSHA256":graph.source_sha256,
        "sourceBytes":Path(path).stat().st_size,
        "nodesInWalkingGraph":len(graph.nodes),
        "directedWalkEdges":sum(len(e) for e in graph.adj.values()),
        "acceptedWalkWays":graph.accepted_ways,
        "blockedBarrierNodes":len(graph.blocked_nodes),
        "mappedOSMBusStopNodes":len(osm_stops),
        "osmStopsWithAtcoTags":sum(
            bool(x["atcoCode"]) for x in graph.transit_stops.values()),
        "unverifiedAnchorCandidates":len(suggestions),
        "osmStopsWithNearbyWalkNode":len(by_stop),
        "diagnosticStopPairs":trials,
        "topologicallyConnectedPairs":connected,
        "topologicallyUnconnectedPairs":rejected,
        "examples":samples,
        "gtfsCrosswalkVerified":False,
        "streetAccessFieldVerified":False,
        "accessibleWalkingProof":False,
        "productionReleaseReady":False
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--city",choices=sorted(CENTRES),required=True)
    p.add_argument("--pbf",required=True)
    p.add_argument("--radius",type=int,default=2500)
    args=p.parse_args(argv)
    result=audit_city(args.city,args.pbf,args.radius)
    print("OPENROAD_OSM_PROBE="+json.dumps(result,sort_keys=True),
          flush=True)


if __name__=="__main__":
    main()

# 2026-10-28: rerun current, off-host source audit; no stop-side field approval implied.
