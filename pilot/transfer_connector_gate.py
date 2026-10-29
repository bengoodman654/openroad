"""Fail-closed, provenance-aware stop-to-pavement walking transfer gate.

This is a release-gated source processing step. Raw OSM nearest neighbour and
matching NaPTAN code are observations, never permission to navigate.
Only independent field-reviewed directional stop-side connectors may enter
the scheduled journey engine. No production API or Android app integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from pilot.gtfs_engine import distance_m
from pilot.journey_options import Footpath
from pilot.pedestrian_graph import (
    PedestrianGraph, StopAnchor, connected_stop_links,
)


@dataclass(frozen=True)
class StopSideReview:
    stop_id: str
    osm_node_id: str
    atco_code: str
    reviewer: str
    reviewed_on: date
    method: str
    evidence_ref: str
    graph_sha256: str
    gtfs_sha256: str
    stop_side: str
    crossing_checked: bool
    pavement_access_checked: bool
    to_graph: bool
    from_graph: bool
    geometry: tuple[tuple[float, float], ...]
    metres: int
    seconds: int
    step_free_confirmed: bool = False


def _review_valid(graph: PedestrianGraph, snapshot, r: StopSideReview,
                  as_of: date, max_age_days: int = 180) -> bool:
    """Check independently sourced evidence; nothing is inferred from proximity."""
    if not isinstance(r, StopSideReview) or not isinstance(r.reviewed_on, date):
        return False
    if r.reviewed_on > as_of or (as_of - r.reviewed_on).days > max_age_days:
        return False
    if r.method not in {"ON_SITE_FIELD_CHECK", "OFFICIAL_STOP_SIDE_SURVEY"}:
        return False
    if not r.reviewer.strip() or not r.evidence_ref.strip():
        return False
    if r.graph_sha256 != graph.source_sha256 or r.gtfs_sha256 != snapshot.source_sha256:
        return False
    if r.stop_id not in snapshot.stops or r.osm_node_id not in graph.nodes:
        return False
    # Exact stop identity must be documented by an official ATCO/NaPTAN code.
    if r.atco_code != r.stop_id or r.stop_side not in {
        "PAVEMENT_BY_STOP", "MARKED_STOP_PLATFORM", "VERIFIED_SHARED_AREA"
    }:
        return False
    if not r.pavement_access_checked or not r.crossing_checked:
        return False
    if not (r.to_graph or r.from_graph):
        return False
    if (r.metres < 0 or r.metres > 100 or r.seconds < 0 or
            len(r.geometry) < 2):
        return False
    if any(len(p) != 2 or not all(isinstance(c, (int, float)) for c in p)
           for p in r.geometry):
        return False
    try:
        stop = snapshot.stops[r.stop_id]
        a = (stop.lat, stop.lon)
        b = graph.nodes[r.osm_node_id]
        if (distance_m(a, r.geometry[0]) > 2 or
                distance_m(b, r.geometry[-1]) > 2):
            return False
        path_length = sum(distance_m(x, y) for x, y in
                          zip(r.geometry, r.geometry[1:]))
        if abs(path_length - r.metres) > max(3.0, 0.1 * r.metres):
            return False
    except (ValueError, TypeError, OverflowError):
        return False
    return True


def independently_reviewed_links(
        graph: PedestrianGraph, snapshot, reviews: Iterable[StopSideReview],
        as_of: date, max_walk_m: int = 600, max_links_per_stop: int = 8,
        avoid_steps: bool = False, cancel_check=None) -> dict:
    """Create only independently reviewed OSM-connected transfer edges.

    Output is research-only; even complete geometrical proof is not a
    guarantee against temporary roadworks or new obstructions.
    """
    metadata = {
        "graphSourceSha256": graph.source_sha256,
        "gtfsSourceSha256": snapshot.source_sha256,
        "evidenceAsOf": as_of.isoformat(),
    }
    valid = []
    rejected = 0
    seen = set()
    for r in reviews:
        if not _review_valid(graph, snapshot, r, as_of):
            rejected += 1
            continue
        if r.stop_id in seen:
            # A duplicated stop-side record is ambiguous; fail the batch.
            return {"outcome": "EVIDENCE_CONFLICT",
                    "links": [], "reviewRejected": rejected + 1,
                    "researchOnly": True, "selectable": False, **metadata}
        seen.add(r.stop_id)
        valid.append(StopAnchor(
            stop_id=r.stop_id, node_id=r.osm_node_id,
            metres=r.metres, seconds=r.seconds,
            geometry=r.geometry, verified=True,
            source=r.evidence_ref,
            to_graph=r.to_graph, from_graph=r.from_graph))
    if len(valid) < 2:
        return {"outcome": "ACCESS_EVIDENCE_MISSING",
                "links": [], "reviewRejected": rejected,
                "researchOnly": True, "selectable": False, **metadata}
    links = connected_stop_links(
        graph, snapshot, valid, max_walk_m=max_walk_m,
        max_per_stop=max_links_per_stop, avoid_steps=avoid_steps,
        cancel_check=cancel_check)
    # A road centreline tagged 'sidewalk=both' is approximate geometry:
    # it cannot become a navigable walking transfer without mapping paths.
    passable = [link for link in links if link.verified]
    return {"outcome": "OK" if passable else "WALK_TOPOLOGY_MISSING",
            "links": passable, "reviewRejected": rejected,
            "researchOnly": True, "selectable": False,
            "accessibilityClaim": "NONE", **metadata}
