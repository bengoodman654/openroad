"""Research-only v2 response envelope: scheduled results never imply readiness.

This is a Python reference contract, NOT an Android/PHP implementation.
The real API must enforce server-issued signed task tickets, pinned dataset
capability manifests and end-to-end authentication before use.
"""
from __future__ import annotations

from datetime import date
import math

from pilot.gtfs_engine import gtfs_utc

OUTCOMES = {
    "OK", "NO_JOURNEY", "COVERAGE_MISSING", "PARTIAL",
    "PROVIDER_UNAVAILABLE", "TIMEOUT", "RATE_LIMITED", "INPUT_INVALID",
    "NO_MATCH", "CANCELLED",
}
FINAL_STATES = {"COMPLETED", "STOPPED", "STOPPING", "UNKNOWN", "RUNNING"}


def _segments_by_trip(snapshot):
    """Index physical segments without manufacturing skipped GTFS stop events."""
    by_trip = {}
    for con in snapshot.connections:
        by_trip.setdefault(con.trip, {})[con.from_sequence] = con
    return by_trip


def _valid_published_bus_leg(connections_by_sequence, leg: dict) -> bool:
    """Board on a real pickup, stay on contiguous events, alight legally."""
    if not connections_by_sequence:
        return False
    starts = [con for con in connections_by_sequence.values()
              if con.a == leg["from"] and
              con.depart == leg["depart"] and con.pickup]
    for current in starts:
        seen = set()
        while current.from_sequence not in seen:
            seen.add(current.from_sequence)
            if (current.b == leg["to"] and
                    current.arrive == leg["arrive"] and current.dropoff):
                return True
            next_event = connections_by_sequence.get(current.to_sequence)
            if (next_event is None or next_event.a != current.b or
                    next_event.depart < current.arrive):
                break
            current = next_event
    return False


def _validate_legs(snapshot, legs: list, segments_by_trip) -> bool:
    if not isinstance(legs, list):
        return False
    last_stop = None
    last_arrival = -1
    for leg in legs:
        if not isinstance(leg, dict):
            return False
        mode = leg.get("mode")
        a, b = leg.get("from"), leg.get("to")
        dep, arr = leg.get("depart"), leg.get("arrive")
        if (mode not in ("BUS", "WALK") or
                a not in snapshot.stops or b not in snapshot.stops or
                not isinstance(dep, int) or not isinstance(arr, int) or
                dep < 0 or arr < dep or dep < last_arrival or
                (last_stop is not None and a != last_stop)):
            return False
        if mode == "BUS":
            occurrence = leg.get("tripOccurrence")
            if not isinstance(occurrence, str):
                return False
            prefix = snapshot.region + ":"
            suffix = ":" + str(snapshot.service_day)
            if not occurrence.startswith(prefix) or not occurrence.endswith(suffix):
                return False
            trip_id = occurrence[len(prefix):-len(suffix)]
            if trip_id not in snapshot.trips:
                return False
            route_key = snapshot.trips[trip_id][0]
            if (leg.get("routeKey") != snapshot.region + ":" + route_key or
                    leg.get("publicLine") != snapshot.routes[route_key][0]):
                return False
            if not _valid_published_bus_leg(segments_by_trip.get(trip_id), leg):
                return False
        else:
            metres = leg.get("metres")
            if (not isinstance(metres, (int, float)) or
                    not math.isfinite(metres) or metres < 0 or
                    not isinstance(leg.get("geometryValidated"), bool)):
                return False
            # Geometry confidence is only an input claim. The independent
            # pavement-side anchor and accessible transfer are not proven.
        last_stop, last_arrival = b, arr
    return True


def envelope(ticket, snapshot, search_result: dict,
             remote_job_status: str = "COMPLETED") -> dict:
    """Fail closed if a stale, cancelled or malformed result reaches the API.

    All itinerary selections remain DISABLED until real capability, walking
    access and acceptance gates have passed. No field verification is inferred.
    """
    if remote_job_status not in FINAL_STATES:
        raise ValueError("Invalid remote job status")
    if not isinstance(search_result, dict):
        raise ValueError("Invalid search result")
    outcome = search_result.get("outcome", "PROVIDER_UNAVAILABLE")
    reason = search_result.get("reasonCode")
    results = search_result.get("results", [])
    if remote_job_status in ("STOPPING", "STOPPED") or outcome == "CANCELLED":
        outcome, reason, results = "CANCELLED", "REQUEST_CANCELLED", []
    elif remote_job_status != "COMPLETED":
        outcome, reason, results = (
            "PROVIDER_UNAVAILABLE", "WORKER_NOT_ACKNOWLEDGED", [])
    elif outcome == "SEARCH_LIMIT":
        outcome, reason, results = "TIMEOUT", "SEARCH_BUDGET_EXHAUSTED", []
    elif outcome not in OUTCOMES:
        outcome, reason, results = (
            "PROVIDER_UNAVAILABLE", "UNKNOWN_ENGINE_OUTCOME", [])
    elif outcome == "OK":
        segments_by_trip = _segments_by_trip(snapshot)
        if (not isinstance(results, list) or not results or
                any(not isinstance(x, dict) or
                    not isinstance(x.get("arrival"), int) or
                    not _validate_legs(snapshot, x.get("legs"), segments_by_trip) or
                    (x["legs"] and x["legs"][-1]["arrive"] != x["arrival"])
                    for x in results)):
            outcome, reason, results = (
                "PROVIDER_UNAVAILABLE", "INVALID_PLANNER_OUTPUT", [])
    else:
        # No failed outcome may accidentally carry clickable route payloads.
        results = []

    # Never use an internal monotonic expiry as a user-visible UTC timestamp.
    # Until a validated manifest exists, published validity is unknown.
    public_results = []
    for x in results:
        legs = []
        for leg in x["legs"]:
            converted = dict(leg)
            converted["departUTC"] = gtfs_utc(
                snapshot.service_day, leg["depart"]).isoformat()
            converted["arriveUTC"] = gtfs_utc(
                snapshot.service_day, leg["arrive"]).isoformat()
            legs.append(converted)
        public_results.append({
            **x, "legs": legs,
            "arrivalUTC": gtfs_utc(
                snapshot.service_day, x["arrival"]).isoformat(),
            "selectable": False,
            "selectionBlocker": "RESEARCH_NOT_PRODUCTION_VERIFIED",
        })

    return {
        "requestId": ticket.task_id,
        "generation": ticket.generation,
        "operationId": ticket.task_id,
        "taskType": "JOURNEY",
        "schemaVersion": "ptv2-research-1",
        "snapshotId": ticket.snapshot_id,
        "outcome": outcome,
        "reasonCode": reason,
        "coverage": {"city": snapshot.city, "region": snapshot.region},
        "provenance": {
            "gtfsSHA256": snapshot.source_sha256,
            "feedVersion": snapshot.feed_version,
            "researchOnly": True,
        },
        "timeBasis": {
            "serviceDate": str(snapshot.service_day),
            "timeZone": "Europe/London",
        },
        "validUntil": None,
        "results": public_results,
        "warnings": ["SCHEDULED_ONLY", "RESEARCH_ONLY"],
        "nextActions": [],
        "realtimeStatus": "SCHEDULED_ONLY",
        "serviceStatus": "SCHEDULED_UNVERIFIED",
        "remoteJobStatus": ("STOPPING" if remote_job_status == "STOPPING"
                            else "STOPPED" if remote_job_status in
                            ("STOPPED", "COMPLETED") else "UNKNOWN"),
    }
