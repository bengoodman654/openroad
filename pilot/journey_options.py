"""Research-only multicriteria scheduled bus planner with explicit footpaths.

Walk edges are supplied by a separate pedestrian router. This module does not
create them from straight-line proximity, and does not imply accessibility.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from heapq import heappush, heappop
from itertools import count

@dataclass(frozen=True)
class Footpath:
    a: str
    b: str
    metres: int
    seconds: int
    verified: bool = False

@dataclass(frozen=True)
class Label:
    stop: str
    arrival: int
    boardings: int
    walked: int
    last_trip: str | None
    steps: tuple

def journey_options(snapshot, origin: str, destination: str, start_sec: int,
                    footpaths=(), max_walk_m: int = 800,
                    max_transfers: int = 2, max_horizon_sec: int = 7200,
                    max_results: int = 3, max_labels: int = 40000):
    """Pareto-label pilot. Uses exact GTFS stops and supplied directional links.

    Output is a range of feasible journeys, not yet a production Pareto proof.
    Boarding restrictions apply at the boarding stop, and alighting
    restrictions apply at the eventual disembarkation stop.
    """
    if origin not in snapshot.stops or destination not in snapshot.stops:
        return {"outcome":"COVERAGE_MISSING","reasonCode":"STOP_OUTSIDE_PILOT_AREA"}
    if start_sec < 0 or max_horizon_sec <= 0 or max_labels <= 0:
        raise ValueError("Invalid search bounds")
    if origin == destination:
        return {"outcome":"OK","results":[{"arrival":start_sec,"legs":[],"transfers":0,"walkedMetres":0}]}
    walks = defaultdict(list)
    for w in footpaths:
        if w.a not in snapshot.stops or w.b not in snapshot.stops:
            raise ValueError("Footpath endpoint outside snapshot")
        if w.metres < 0 or w.seconds <= 0 or w.a == w.b:
            raise ValueError("Invalid footpath")
        walks[w.a].append(w)
    # Consecutive GTFS edges of a trip are grouped before generating
    # alighting choices. Never leap over a missing/clipped connection.
    by_trip = defaultdict(list)
    for c in snapshot.connections:
        by_trip[c.trip].append(c)
    departures = defaultdict(list)
    for trip, segments in by_trip.items():
        segments.sort(key=lambda x:(x.depart,x.arrive,x.a))
        for i,c in enumerate(segments):
            if not c.pickup:
                continue
            t = c.depart
            prev = c.a
            for edge in segments[i:]:
                if edge.a != prev or edge.depart < t:
                    break
                if edge.dropoff and edge.arrive >= c.depart:
                    departures[c.a].append((c.depart,edge.arrive,trip,edge.b))
                prev = edge.b
                t = edge.arrive
    for values in departures.values():
        values.sort()
    seq=count()
    root=Label(origin,start_sec,0,0,None,())
    queue=[(start_sec,next(seq),root)]
    frontier=defaultdict(list)
    frontier[(origin,None)].append(root)
    solutions=[]
    expanded=0
    end_time=start_sec+max_horizon_sec
    def offer(new):
        key=(new.stop,new.last_trip)
        existing=frontier[key]
        # Equal arrival, boarding and walking totals cannot justify keeping
        # another label at this particular state.
        if any(q.arrival<=new.arrival and q.boardings<=new.boardings
               and q.walked<=new.walked for q in existing):
            return
        frontier[key]=[q for q in existing if not (
            new.arrival<=q.arrival and new.boardings<=q.boardings
            and new.walked<=q.walked)]+[new]
        heappush(queue,(new.arrival,next(seq),new))
    while queue:
        _,_,p=heappop(queue)
        if p not in frontier[(p.stop,p.last_trip)]:
            continue
        expanded+=1
        if expanded>max_labels:
            return {"outcome":"SEARCH_LIMIT","reasonCode":"LABEL_BUDGET",
                    "expandedLabels":expanded}
        if p.stop==destination:
            solutions.append(p)
            continue
        for w in walks[p.stop]:
            if p.walked+w.metres>max_walk_m or p.arrival+w.seconds>end_time:
                continue
            step={"mode":"WALK","from":w.a,"to":w.b,
                  "depart":p.arrival,"arrive":p.arrival+w.seconds,
                  "metres":w.metres,"geometryValidated":w.verified}
            offer(Label(w.b,p.arrival+w.seconds,p.boardings,
                        p.walked,None,p.steps+(step,)))
        if p.boardings>max_transfers:
            continue
        for dep,arr,trip,to_stop in departures[p.stop]:
            if dep<p.arrival or arr>end_time:
                continue
            boardings=p.boardings+1
            if boardings>max_transfers+1:
                continue
            route=snapshot.trips[trip][0]
            leg={"mode":"BUS","from":p.stop,"to":to_stop,
                 "depart":dep,"arrive":arr,"tripOccurrence":
                 f"{snapshot.region}:{trip}:{snapshot.service_day}",
                 "publicLine":snapshot.routes[route][0]}
            offer(Label(to_stop,arr,boardings,p.walked,trip,p.steps+(leg,)))
    candidates=[]
    seen=set()
    for p in sorted(solutions,key=lambda p:(p.arrival,p.boardings,p.walked)):
        sig=tuple((s["mode"],s.get("tripOccurrence"),s["from"],s["to"]) for s in p.steps)
        if sig in seen:
            continue
        seen.add(sig)
        candidates.append({"arrival":p.arrival,"legs":list(p.steps),
                           "transfers":max(0,p.boardings-1),
                           "walkedMetres":p.walked,
                           "warnings":["SCHEDULED_ONLY"]+
                            (["UNVERIFIED_WALK_GEOMETRY","NO_ACCESSIBILITY_PROOF"]
                             if any(s["mode"]=="WALK" and not s["geometryValidated"]
                                    for s in p.steps) else [])})
    # Keep nondominated end-to-end labels only, then select distinct patterns.
    nondominated=[]
    for r in candidates:
        if any(q["arrival"]<=r["arrival"] and q["transfers"]<=r["transfers"] and
               q["walkedMetres"]<=r["walkedMetres"] for q in nondominated):
            continue
        nondominated.append(r)
    if not nondominated:
        return {"outcome":"NO_JOURNEY","reasonCode":"NO_FEASIBLE_SCHEDULED_CONNECTION","results":[]}
    return {"outcome":"OK","results":nondominated[:max_results],
            "expandedLabels":expanded,"researchOnly":True}
