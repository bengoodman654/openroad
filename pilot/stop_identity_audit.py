"""Off-host exact GTFS/OSM ATCO identity audit. No walking links are created.

An exact code and proximity match is NOT evidence of pavement-side boarding
access, a safe crossing, a legal route or step-free accessibility.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date
import json
import math

from pilot.gtfs_engine import CENTRES, distance_m, load_region
from pilot.pedestrian_graph import load_osm_pbf_offhost


def audit_stop_codes(snapshot, graph, radius_m: int = 2500,
                     near_m: float = 40.0) -> dict:
    if snapshot.city not in CENTRES or not 100 <= radius_m <= 15000:
        raise ValueError("Unsupported city or audit radius")
    if not 0 < near_m <= 200:
        raise ValueError("Invalid stop-match threshold")
    centre = CENTRES[snapshot.city]
    local_stops = sorted(
        (s for s in snapshot.stops.values()
         if distance_m((s.lat, s.lon), centre) <= radius_m),
        key=lambda s: s.id)
    by_atco = defaultdict(list)
    for node in graph.transit_stops.values():
        code = str(node.get("atcoCode") or "").strip().upper()
        lat, lon = node.get("lat"), node.get("lon")
        if (not code or not isinstance(lat, (int, float)) or
                not isinstance(lon, (int, float)) or
                not math.isfinite(lat) or not math.isfinite(lon) or
                not (-90 <= lat <= 90 and -180 <= lon <= 180)):
            continue
        by_atco[code].append(node)

    counts = {
        "EXACT_TAG_NEAR_UNVERIFIED": 0,
        "EXACT_TAG_DISTANT_REVIEW": 0,
        "DUPLICATE_TAG_REVIEW": 0,
        "NO_EXACT_TAG": 0,
    }
    examples = []
    for stop in local_stops:
        possible = by_atco.get(stop.id.strip().upper(), ())
        if not possible:
            status, metres = "NO_EXACT_TAG", None
        elif len(possible) != 1:
            status, metres = "DUPLICATE_TAG_REVIEW", None
        else:
            match = possible[0]
            metres = distance_m((stop.lat, stop.lon),
                                (match["lat"], match["lon"]))
            status = ("EXACT_TAG_NEAR_UNVERIFIED" if metres <= near_m
                      else "EXACT_TAG_DISTANT_REVIEW")
        counts[status] += 1
        if len(examples) < 12 and status != "EXACT_TAG_NEAR_UNVERIFIED":
            examples.append({
                "gtfsStopId": stop.id,
                "status": status,
                "straightLineMetres": round(metres, 1)
                if metres is not None else None,
            })
    assert sum(counts.values()) == len(local_stops)
    return {
        "city": snapshot.city,
        "serviceDate": str(snapshot.service_day),
        "gtfsSourceSHA256": snapshot.source_sha256,
        "osmSourceSHA256": graph.source_sha256,
        "radiusMetres": radius_m,
        "nearThresholdMetres": near_m,
        "gtfsStopsWithinRadius": len(local_stops),
        "statusCounts": counts,
        "reviewExamples": examples,
        "identityStatus": "RESEARCH_ONLY_CODE_MATCHES_UNVERIFIED",
        "autoVerifiedStopAnchors": 0,
        "walkingSafetyConfirmed": False,
        "accessibilityConfirmed": False,
        "usableInRouting": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=sorted(CENTRES), required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--gtfs", required=True)
    parser.add_argument("--osm", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--radius", type=int, default=2500)
    args = parser.parse_args(argv)
    snapshot = load_region(
        args.gtfs, args.city, args.region, date.fromisoformat(args.date),
        radius_m=args.radius)
    graph = load_osm_pbf_offhost(
        args.osm, centre=CENTRES[args.city], radius_m=args.radius)
    print("OPENROAD_EXACT_STOP_CODE_AUDIT=" +
          json.dumps(audit_stop_codes(snapshot, graph, args.radius),
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
