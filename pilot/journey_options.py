"""Research-only, bounded Pareto bus planner using an on-demand scan.

Walking transfers are accepted ONLY as explicit directional footpath edges from
a separate pedestrian data source; none are invented from straight-line range.
No rail, realtime, mobility-accessibility or production-SLA claims.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count


@dataclass(frozen=True)
class Footpath:
    a: str
    b: str
    metres: int
    seconds: int
    verified: bool = False


@dataclass(eq=False, frozen=True)
class Label:
    stop: str
    arrival: int
    ready: int
    boardings: int
    walked: int
    steps: tuple
    trip: str | None = None
    last_sequence: int = 0


class _BudgetExceeded(Exception):
    pass


def _dominates(a: Label, b: Label) -> bool:
    # Earlier stop arrival is not enough: readiness for the next boarding
    # also reflects time spent meeting the interchange buffer.
    return (a.arrival <= b.arrival and a.ready <= b.ready and
            a.boardings <= b.boardings and a.walked <= b.walked)


def journey_options(snapshot, origin: str, destination: str, start_sec: int,
                    footpaths=(), max_walk_m: int = 800,
                    max_transfers: int = 2, max_horizon_sec: int = 7200,
                    max_results: int = 3, max_labels: int = 40000,
                    transfer_seconds: int = 120) -> dict:
    """Find bounded Pareto scheduled-bus paths between exact stop IDs.

    Every GTFS connection is scanned once; there is no quadratic expansion
    into all possible onboard origin/destination pairs. For a new trip, a
    boarding consumes one permitted bus. Staying onboard never consumes a
    transfer, including while passing stops with no alighting permission.

    Result is provisional research, NOT a production route recommendation.
    """
    if origin not in snapshot.stops or destination not in snapshot.stops:
        return {"outcome": "COVERAGE_MISSING",
                "reasonCode": "STOP_OUTSIDE_PILOT_AREA"}
    if (start_sec < 0 or max_horizon_sec <= 0 or max_labels <= 0 or
            max_results <= 0 or max_walk_m < 0 or max_transfers < 0 or
            transfer_seconds < 0):
        raise ValueError("Invalid search bounds")
    if origin == destination:
        return {"outcome": "OK", "results": [{
            "arrival": start_sec, "legs": [], "transfers": 0,
            "walkedMetres": 0, "warnings": ["SCHEDULED_ONLY"]}],
            "expandedLabels": 0, "researchOnly": True}

    walks = defaultdict(list)
    for w in footpaths:
        if w.a not in snapshot.stops or w.b not in snapshot.stops:
            raise ValueError("Footpath endpoint outside snapshot")
        if (w.metres < 0 or w.seconds <= 0 or w.a == w.b or
                not isinstance(w.verified, bool)):
            raise ValueError("Invalid footpath")
        walks[w.a].append(w)

    end_time = start_sec + max_horizon_sec
    serial = count()
    walking_queue = []
    frontier = defaultdict(list)  # stop -> nondominated offboard labels
    onboard = {}  # trip -> labels that rode its immediately preceding edge
    accepted_labels = 0
    root = Label(origin, start_sec, start_sec, 0, 0, ())
    frontier[origin].append(root)

    def offer(p: Label):
        nonlocal accepted_labels
        labels = frontier[p.stop]
        if p.arrival > end_time or any(_dominates(q, p) for q in labels):
            return
        frontier[p.stop] = [q for q in labels if not _dominates(p, q)] + [p]
        accepted_labels += 1
        if accepted_labels > max_labels:
            raise _BudgetExceeded()
        heappush(walking_queue, (p.arrival, next(serial), p))

    def walk_closure():
        # Reachability through multiple directional, explicitly supplied
        # pedestrian links, including after getting off a bus.
        while walking_queue:
            _, _, p = heappop(walking_queue)
            if p not in frontier[p.stop]:
                continue
            for w in walks[p.stop]:
                if p.walked + w.metres > max_walk_m:
                    continue
                arrival = p.arrival + w.seconds
                if arrival > end_time:
                    continue
                step = {"mode": "WALK", "from": w.a, "to": w.b,
                        "depart": p.arrival, "arrive": arrival,
                        "metres": w.metres,
                        "geometryValidated": w.verified}
                offer(Label(w.b, arrival, max(arrival, p.ready),
                            p.boardings, p.walked + w.metres,
                            p.steps + (step,)))

    def prune_onboard(labels):
        # All candidates reach the same scheduled trip edge endpoint and
        # have the same departure/arrival; preserve cost-distinct histories.
        keep = []
        for p in labels:
            if any(_dominates(q, p) for q in keep):
                continue
            keep = [q for q in keep if not _dominates(p, q)]
            keep.append(p)
        return keep

    try:
        heappush(walking_queue, (root.arrival, next(serial), root))
        walk_closure()
        # Snapshot connections are already sorted by departure in load_region.
        for con in snapshot.connections:
            if con.depart < start_sec:
                continue
            if con.depart > end_time:
                break
            if con.arrive > end_time:
                continue
            boarding = []
            if con.pickup:
                for p in frontier.get(con.a, ()):
                    if p.ready > con.depart or p.boardings >= max_transfers + 1:
                        continue
                    route = snapshot.trips[con.trip][0]
                    step = {"mode": "BUS", "from": con.a, "to": con.b,
                            "fromName": snapshot.stops[con.a].name,
                            "toName": snapshot.stops[con.b].name,
                            "depart": con.depart, "arrive": con.arrive,
                            "tripOccurrence": (
                                f"{snapshot.region}:{con.trip}:{snapshot.service_day}"),
                            "publicLine": snapshot.routes[route][0],
                            "routeKey": f"{snapshot.region}:{route}"}
                    boarding.append(Label(con.b, con.arrive,
                                          con.arrive + transfer_seconds,
                                          p.boardings + 1, p.walked,
                                          p.steps + (step,), con.trip,
                                          con.to_sequence))
            # Continuing is independent of pickup/dropoff restrictions. The
            # sequence IDs rule out skipping a clipped outside-area section,
            # even when the same stop appears twice on a circular service.
            continuing = []
            for p in onboard.get(con.trip, ()):
                if (p.stop != con.a or p.arrival > con.depart or
                        (p.last_sequence and con.from_sequence and
                         p.last_sequence != con.from_sequence)):
                    continue
                prior = p.steps[-1]
                step = {**prior, "to": con.b,
                        "toName": snapshot.stops[con.b].name,
                        "arrive": con.arrive}
                continuing.append(Label(con.b, con.arrive,
                                        con.arrive + transfer_seconds,
                                        p.boardings, p.walked,
                                        p.steps[:-1] + (step,), con.trip,
                                        con.to_sequence))
            next_onboard = prune_onboard(boarding + continuing)
            if next_onboard:
                accepted_labels += len(next_onboard)
                if accepted_labels > max_labels:
                    raise _BudgetExceeded()
                onboard[con.trip] = next_onboard
            else:
                onboard.pop(con.trip, None)
            if con.dropoff:
                for p in next_onboard:
                    # The stop is usable only when alighting is permitted.
                    offer(p)
                walk_closure()
    except _BudgetExceeded:
        return {"outcome": "SEARCH_LIMIT", "reasonCode": "LABEL_BUDGET",
                "expandedLabels": accepted_labels, "researchOnly": True}

    results = []
    for p in sorted(frontier.get(destination, ()),
                    key=lambda q: (q.arrival, q.boardings, q.walked)):
        if any(_dominates(q, p) for q in frontier[destination] if q is not p):
            continue
        result = {"arrival": p.arrival, "legs": list(p.steps),
                  "transfers": max(0, p.boardings - 1),
                  "walkedMetres": p.walked,
                  "warnings": ["SCHEDULED_ONLY"]}
        walked_legs = [step for step in p.steps if step["mode"] == "WALK"]
        if walked_legs:
            if any(not step["geometryValidated"] for step in walked_legs):
                result["warnings"].append("UNVERIFIED_WALK_GEOMETRY")
            # A verified path shape is NOT evidence of step-free access.
            result["warnings"].append("NO_ACCESSIBILITY_PROOF")
        results.append(result)
        if len(results) >= max_results:
            break
    if not results:
        return {"outcome": "NO_JOURNEY",
                "reasonCode": "NO_FEASIBLE_SCHEDULED_CONNECTION",
                "results": [], "researchOnly": True}
    return {"outcome": "OK", "results": results,
            "expandedLabels": accepted_labels, "researchOnly": True}
