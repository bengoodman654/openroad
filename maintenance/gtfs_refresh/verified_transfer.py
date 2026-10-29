"""Source-pinned bridge from independently reviewed OSM stop-side links to
the immutable off-host SQLite timetable search.

Never constructs an edge from geographic proximity or matching stop codes.
All outputs remain research-only, non-navigable scheduled itineraries.
"""
from __future__ import annotations

from collections import defaultdict
import math
from pilot.gtfs_engine import distance_m
from pilot.journey_options import Footpath


def reviewed_transfer_links(db, index_info: dict, certified: dict | None,
                            max_walk_metres: int, avoid_steps: bool = False):
    """Validate *all* imported walking links or reject the whole batch.

    The caller must first run pilot.transfer_connector_gate with independently
    reviewed boarding-kerb connector evidence and a complete-ways OSM graph.
    A matching GTFS/OSM hash is mandatory. We intentionally do not accept
    arbitrary JSON geometry or auto-nearest-neighbour candidate points.
    """
    if certified is None:
        return {}
    if not isinstance(certified, dict):
        raise ValueError("Expected field-reviewed walking bundle")
    if (certified.get("researchOnly") is not True or
            certified.get("selectable") is not False or
            certified.get("outcome") != "OK" or
            certified.get("accessibilityClaim") != "NONE"):
        raise ValueError("Walking transfer evidence is not releasable")
    source = index_info.get("sourceArchiveSha256")
    graph = certified.get("graphSourceSha256")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("GTFS source provenance missing")
    if certified.get("gtfsSourceSha256") != source:
        raise ValueError("Walking review belongs to a different GTFS snapshot")
    if not isinstance(graph, str) or not graph:
        raise ValueError("OSM source provenance missing")
    links = certified.get("links")
    if not isinstance(links, list) or not 0 < len(links) <= 2000:
        raise ValueError("Empty or unbounded walking transfer evidence")
    ids = {stop for walk in links for stop in (getattr(walk,"a",None),
                                                getattr(walk,"b",None))
           if isinstance(stop,str)}
    if len(ids) > 2000 or not ids:
        raise ValueError("Unexpected walking stop identities")
    places={}
    # Keep SQLite parameter count under portability limits.
    for stop in sorted(ids):
        row=db.execute("SELECT lat,lon FROM stops WHERE stop_id=?",(stop,)).fetchone()
        if row is None:raise ValueError("Reviewed stop absent from active timetable")
        places[stop]=(float(row[0]),float(row[1]))
    incoming=defaultdict(list)
    seen=set()
    for walk in links:
        if not isinstance(walk, Footpath):
            raise ValueError("Untrusted walking geometry")
        if (walk.a == walk.b or not walk.verified or
            walk.provider != "OpenStreetMap" or
            walk.source_sha256 != graph or
            walk.metres <= 0 or walk.seconds <= 0 or
            walk.seconds > 3600):
            raise ValueError("Invalid reviewed walking transfer")
        # A valid but over-limit or stair-using connector is ineligible,
        # not evidence that the underlying GTFS/OSM source is corrupted.
        if walk.metres > max_walk_metres or (avoid_steps and walk.includes_steps):
            continue
        if (walk.a,walk.b) in seen:
            raise ValueError("Ambiguous duplicate walking transfer")
        seen.add((walk.a,walk.b))
        if len(walk.geometry) < 2 or len(walk.geometry) > 10000:
            raise ValueError("Missing or unbounded walking vertices")
        if any((not isinstance(p,(tuple,list)) or len(p)!=2 or
                any(not isinstance(v,(float,int)) or not math.isfinite(v)
                    for v in p)) for p in walk.geometry):
            raise ValueError("Invalid walking path coordinates")
        if (distance_m(walk.geometry[0],places[walk.a]) > 2.0 or
            distance_m(walk.geometry[-1],places[walk.b]) > 2.0):
            raise ValueError("Walking geometry does not meet the stops")
        length=sum(distance_m(x,y) for x,y in zip(walk.geometry,walk.geometry[1:]))
        if abs(length-walk.metres) > max(12.0,walk.metres*0.22):
            raise ValueError("Walking path distance does not match measured path")
        incoming[walk.b].append(walk)
    for key in incoming:
        incoming[key].sort(key=lambda w:(w.seconds,w.metres,w.a))
    return dict(incoming)
