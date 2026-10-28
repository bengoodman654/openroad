"""Research-only walking graph built OFF-HOST from explicit path topology.

This never treats geographic closeness, line crossings or automatic GTFS-stop
snapping as proof of a walkable connection. OSM parsing needs optional
pyosmium on the external builder; routing and fixture tests use stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from collections import defaultdict
import hashlib
import math

from pilot.gtfs_engine import distance_m
from pilot.journey_options import Footpath
from pilot.request_lifecycle import raise_if_cancelled

# Conservative starting whitelist. Major roads need an independently mapped
# usable pedestrian facility; incomplete crossings and access tags fail shut.
WALKWAYS = {"footway", "pedestrian", "path", "living_street", "corridor",
            "steps", "platform"}
SIDEWALK_ROADS = {"residential", "service", "unclassified", "tertiary",
                  "secondary", "primary"}
YES = {"yes", "designated", "permissive"}
NO = {"no", "private", "destination", "customers", "delivery"}
SIDEWALKS = {"yes", "both", "left", "right"}


def allows_pedestrians(tags: dict[str, str]) -> bool:
    """Reject ambiguous access and unmarked busy-road walk segments."""
    highway = tags.get("highway", "")
    if tags.get("area") == "yes" or tags.get("highway") in (
            "construction", "proposed"):
        return False
    if tags.get("oneway:foot", "").lower() not in (
            "", "yes", "1", "true", "-1", "no", "0", "false"):
        return False
    foot = tags.get("foot", "")
    if foot in NO or tags.get("foot:conditional"):
        return False
    if tags.get("access", "") in NO and foot not in YES:
        return False
    if tags.get("access:conditional"):
        return False
    if highway in WALKWAYS:
        return True
    if highway == "cycleway":
        return foot in YES
    if highway in SIDEWALK_ROADS:
        return foot in YES or tags.get("sidewalk") in SIDEWALKS
    return False


def foot_direction(tags: dict[str, str]) -> int:
    """Vehicle-only `oneway` does NOT automatically restrict pedestrians."""
    value = tags.get("oneway:foot", "").lower()
    if value in {"yes", "1", "true"}:
        return 1
    if value == "-1":
        return -1
    return 0


@dataclass(frozen=True, slots=True)
class Edge:
    target: str
    metres: int
    seconds: int
    steps: bool
    way_id: str
    mapped_foot_geometry: bool


@dataclass(frozen=True, slots=True)
class WalkingRoute:
    node_ids: tuple[str, ...]
    geometry: tuple[tuple[float, float], ...]
    metres: int
    seconds: int
    includes_steps: bool
    mapped_foot_geometry: bool


@dataclass(frozen=True, slots=True)
class StopAnchor:
    """Externally checked pavement connection, GTFS stop -> OSM graph node.

    No geometry-free nearest-neighbour 'snapping' is permitted in routing.
    """
    stop_id: str
    node_id: str
    metres: int
    seconds: int
    geometry: tuple[tuple[float, float], ...]
    verified: bool
    source: str
    to_graph: bool = True
    from_graph: bool = True


class PedestrianGraph:
    def __init__(self, source_sha256: str, walking_speed_mps: float = 1.25):
        if not source_sha256 or not (0.5 <= walking_speed_mps <= 2.0):
            raise ValueError("Graph needs source identity and realistic speed")
        self.source_sha256 = source_sha256
        self.speed = walking_speed_mps
        self.nodes: dict[str, tuple[float, float]] = {}
        self.adj: dict[str, list[Edge]] = {}
        self.blocked_nodes: set[str] = set()
        self.accepted_ways = 0
        self.discarded_ways = 0
        self.transit_stops: dict[str, dict] = {}

    def block_node(self, node_id: str):
        self.blocked_nodes.add(str(node_id))

    def add_way(self, way_id: str, vertices, tags: dict[str, str]) -> bool:
        """Add adjacent OSM node pairs, never crossing unshared intersections."""
        if not allows_pedestrians(tags):
            self.discarded_ways += 1
            return False
        points = tuple((str(i), float(lat), float(lon))
                       for i, lat, lon in vertices)
        if len(points) < 2 or any(
            not (math.isfinite(lat) and math.isfinite(lon) and
                 -90 <= lat <= 90 and -180 <= lon <= 180)
            for _, lat, lon in points):
            self.discarded_ways += 1
            return False
        # Do not partially mutate the graph for inconsistent source geometry.
        for node, lat, lon in points:
            existing = self.nodes.get(node)
            if existing and distance_m(existing, (lat, lon)) > 1.5:
                raise ValueError("Conflicting coordinates for OSM node")
        for node, lat, lon in points:
            self.nodes[node] = (lat, lon)
        direction = foot_direction(tags)
        steps = tags.get("highway") == "steps"
        mapped = tags.get("highway") in WALKWAYS
        for a, b in zip(points, points[1:]):
            if a[0] == b[0]:
                continue
            metres = max(1, math.ceil(distance_m(a[1:], b[1:])))
            speed = min(self.speed, 0.7) if steps else self.speed
            seconds = max(1, math.ceil(metres / speed))
            if direction >= 0:
                self.adj.setdefault(a[0], []).append(
                    Edge(b[0], metres, seconds, steps, str(way_id), mapped))
            if direction <= 0:
                self.adj.setdefault(b[0], []).append(
                    Edge(a[0], metres, seconds, steps, str(way_id), mapped))
        self.accepted_ways += 1
        return True

    def route(self, origin_node: str, target_node: str,
              max_walk_m: int = 800, avoid_steps: bool = False,
              cancel_check=None) -> WalkingRoute | None:
        """Shortest-distance walk through real graph edges, bounded by metres.

        It is NOT a wheelchair-accessibility test. Even avoiding mapped steps
        does not prove kerbs, crossings, widths or surface suitability.
        """
        if max_walk_m < 0:
            raise ValueError("Invalid walking limit")
        raise_if_cancelled(cancel_check)
        if (origin_node not in self.nodes or target_node not in self.nodes
                or origin_node in self.blocked_nodes
                or target_node in self.blocked_nodes):
            return None
        if origin_node == target_node:
            return WalkingRoute((origin_node,),
                                (self.nodes[origin_node],), 0, 0, False, True)
        serial = count()
        queue = [(0, 0, next(serial), origin_node)]
        best = {origin_node: (0, 0)}
        parent = {}
        visit_index = 0
        while queue:
            if visit_index % 32 == 0:
                raise_if_cancelled(cancel_check)
            visit_index += 1
            metres, seconds, _, node = heappop(queue)
            if (metres, seconds) != best.get(node):
                continue
            if node == target_node:
                path = [node]
                includes_steps = False
                mapped_geometry = True
                while node in parent:
                    previous, edge = parent[node]
                    includes_steps |= edge.steps
                    mapped_geometry &= edge.mapped_foot_geometry
                    node = previous
                    path.append(node)
                path.reverse()
                return WalkingRoute(
                    tuple(path), tuple(self.nodes[n] for n in path),
                    metres, seconds, includes_steps, mapped_geometry)
            for edge_index, edge in enumerate(self.adj.get(node, ())):
                if edge_index % 64 == 0:
                    raise_if_cancelled(cancel_check)
                if (edge.target in self.blocked_nodes or
                        (avoid_steps and edge.steps)):
                    continue
                dm = metres + edge.metres
                if dm > max_walk_m:
                    continue
                ds = seconds + edge.seconds
                if (dm, ds) < best.get(edge.target, (math.inf, math.inf)):
                    best[edge.target] = (dm, ds)
                    parent[edge.target] = (node, edge)
                    heappush(queue, (dm, ds, next(serial), edge.target))
        return None


def _anchor_checked(graph: PedestrianGraph, snapshot, anchor: StopAnchor):
    if not anchor.verified or not anchor.source:
        raise ValueError("No independently verified GTFS-to-path connector")
    if anchor.stop_id not in snapshot.stops or anchor.node_id not in graph.nodes:
        raise ValueError("Unrecognised anchor endpoint")
    if anchor.metres < 0 or anchor.seconds < 0 or len(anchor.geometry) < 2:
        raise ValueError("Invalid anchor dimensions")
    s = snapshot.stops[anchor.stop_id]
    source_location = (s.lat, s.lon)
    node_location = graph.nodes[anchor.node_id]
    if (distance_m(anchor.geometry[0], source_location) > 2.0 or
            distance_m(anchor.geometry[-1], node_location) > 2.0):
        raise ValueError("Anchor geometry does not connect stop to graph node")
    # Reject obviously falsified distance but allow source measurement
    # rounding / map precision.
    length = sum(distance_m(a, b) for a, b in
                 zip(anchor.geometry, anchor.geometry[1:]))
    if abs(length - anchor.metres) > max(3.0, 0.1 * anchor.metres):
        raise ValueError("Anchor distance inconsistent with its geometry")


def link_stops(graph: PedestrianGraph, snapshot,
               from_anchor: StopAnchor, to_anchor: StopAnchor,
               max_walk_m: int = 800, avoid_steps: bool = False,
               cancel_check=None) -> Footpath | None:
    """Build one genuinely connected, directional route between GTFS stops.

    Both sidewalk connectors must be independently validated. A straight line
    or even a close OSM node is never automatically made a routable edge.
    """
    raise_if_cancelled(cancel_check)
    if from_anchor.stop_id == to_anchor.stop_id:
        return None
    _anchor_checked(graph, snapshot, from_anchor)
    _anchor_checked(graph, snapshot, to_anchor)
    if not from_anchor.to_graph or not to_anchor.from_graph:
        return None
    allowance = max_walk_m - from_anchor.metres - to_anchor.metres
    if allowance < 0:
        return None
    walked = graph.route(from_anchor.node_id, to_anchor.node_id,
                         allowance, avoid_steps=avoid_steps,
                         cancel_check=cancel_check)
    if walked is None:
        return None
    metres = from_anchor.metres + walked.metres + to_anchor.metres
    seconds = max(1, from_anchor.seconds + walked.seconds + to_anchor.seconds)
    # Include exact path corners from the input, preserving stop-side
    # connectors and the actual network vertices for rendering on a map.
    vertices = (tuple(from_anchor.geometry) + walked.geometry[1:] +
                tuple(reversed(to_anchor.geometry))[1:])
    geometry = []
    for point in vertices:
        if not geometry or distance_m(geometry[-1], point) > 0.05:
            geometry.append(point)
    if len(geometry) == 1:
        geometry.append(geometry[0])
    return Footpath(
        from_anchor.stop_id, to_anchor.stop_id, metres, seconds,
        walked.mapped_foot_geometry, tuple(geometry), "OpenStreetMap",
        graph.source_sha256, walked.includes_steps)


def connected_stop_links(graph: PedestrianGraph, snapshot, anchors,
                         max_walk_m: int = 600, max_per_stop: int = 8,
                         avoid_steps: bool = False, cancel_check=None):
    """OFF-HOST candidate generation; output only verified routed links.

    A great-circle radius is merely a cheap LOWER-BOUND rejection. It NEVER
    supplies a walking edge. All included links use actual Dijkstra paths.
    """
    if max_per_stop < 1:
        raise ValueError("Invalid footpath density")
    raise_if_cancelled(cancel_check)
    validated = {}
    for anchor in anchors:
        _anchor_checked(graph, snapshot, anchor)
        if anchor.stop_id in validated:
            raise ValueError("Ambiguous multiple anchors for stop")
        validated[anchor.stop_id] = anchor
    stops = list(validated)
    out = []
    for a in stops:
        raise_if_cancelled(cancel_check)
        s = snapshot.stops[a]
        options = []
        for option_index, b in enumerate(stops):
            if option_index % 32 == 0:
                raise_if_cancelled(cancel_check)
            if a == b:
                continue
            t = snapshot.stops[b]
            if distance_m((s.lat, s.lon), (t.lat, t.lon)) > max_walk_m:
                continue
            route = link_stops(graph, snapshot, validated[a], validated[b],
                               max_walk_m, avoid_steps=avoid_steps,
                               cancel_check=cancel_check)
            if route is not None:
                options.append(route)
        options.sort(key=lambda w: (w.seconds, w.metres, w.b))
        out.extend(options[:max_per_stop])
    return out


@dataclass(frozen=True, slots=True)
class StopCandidate:
    stop_id: str
    node_id: str
    metres_straight_line: int
    status: str = "UNVERIFIED_NOT_ROUTABLE"


def propose_stop_anchors(graph: PedestrianGraph, snapshot,
                         max_snap_m: int = 40, max_candidates: int = 3
                         ) -> list[StopCandidate]:
    """Spatially shortlist OSM nodes; suggestions can NEVER be routed.

    A separate independent connector check must establish usable crossing,
    pavement side, entrance, permissions and actual path geometry before a
    candidate can become a verified StopAnchor.
    """
    if not 0 < max_snap_m <= 200 or max_candidates < 1:
        raise ValueError("Invalid anchor search bounds")
    cell_size = 0.001  # coarse latitude/longitude buckets, not walking metres
    cells = defaultdict(list)
    for node, (lat, lon) in graph.nodes.items():
        if node not in graph.blocked_nodes:
            cells[(math.floor(lat/cell_size), math.floor(lon/cell_size))].append(node)
    candidates = []
    for stop in snapshot.stops.values():
        lat_radius = max_snap_m / 110000.0
        lon_radius = max_snap_m / max(1000.0, 111000.0 *
                                      abs(math.cos(math.radians(stop.lat))))
        ilat = math.floor(stop.lat/cell_size)
        ilon = math.floor(stop.lon/cell_size)
        di = math.ceil(lat_radius/cell_size) + 1
        dj = math.ceil(lon_radius/cell_size) + 1
        neighbours = []
        for i in range(ilat-di, ilat+di+1):
            for j in range(ilon-dj, ilon+dj+1):
                for node in cells.get((i,j), ()):
                    dist = distance_m((stop.lat,stop.lon),graph.nodes[node])
                    if dist <= max_snap_m:
                        neighbours.append((dist,node))
        for dist, node in sorted(neighbours)[:max_candidates]:
            candidates.append(StopCandidate(stop.id,node,math.ceil(dist)))
    return candidates


def load_osm_pbf_offhost(path: str, source_sha256: str | None = None,
                         centre: tuple[float, float] | None = None,
                         radius_m: int = 2500
                        ) -> PedestrianGraph:
    """Optional pyosmium adapter: run ONLY on a small, complete-ways extract.

    Extract with 'osmium extract --strategy complete_ways' on a proper build
    worker. NEVER feed an entire country extract to the shared web host.
    Missing locations cause rejection, not imaginary joinery.
    """
    try:
        import osmium
    except ImportError as e:
        raise RuntimeError("Off-host builder needs optional pyosmium") from e
    if centre is not None and (radius_m < 100 or radius_m > 15000):
        raise ValueError("Invalid city extract radius")
    if not source_sha256:
        sha = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        source_sha256 = sha.hexdigest()
    graph = PedestrianGraph(source_sha256)

    class Loader(osmium.SimpleHandler):
        def node(self, n):
            tags = dict(n.tags)
            if (tags.get("barrier") in {"wall", "fence", "turnstile"} or
                    (tags.get("barrier") == "gate" and
                     (tags.get("access") in NO or tags.get("foot") in NO))):
                graph.block_node(str(n.id))
            # An OSM bus-stop tag is only an UNVERIFIED crosswalk candidate.
            # It is never promoted to a GTFS stop-access connector.
            if (tags.get("highway") == "bus_stop" or
                    (tags.get("public_transport") == "platform" and
                     tags.get("bus") == "yes")):
                try:
                    if not n.location.valid():
                        return
                    point = (float(n.location.lat), float(n.location.lon))
                except (ValueError, TypeError, RuntimeError):
                    return
                if centre is not None and distance_m(point,centre) > radius_m:
                    return
                graph.transit_stops[str(n.id)] = {
                    "osmNode": str(n.id),
                    "atcoCode": tags.get("naptan:AtcoCode", ""),
                    "name": tags.get("name", ""),
                    "lat": point[0], "lon": point[1],
                    "crosswalk": "UNVERIFIED_OSM_TAG",
                }

        def way(self, way):
            tags = dict(way.tags)
            if not allows_pedestrians(tags):
                return
            vertices = []
            for node in way.nodes:
                try:
                    if not node.location.valid():
                        return
                    vertices.append((str(node.ref),
                                     float(node.location.lat),
                                     float(node.location.lon)))
                except (ValueError, TypeError, RuntimeError):
                    return
            if centre is not None and not any(
                    distance_m((lat,lon),centre) <= radius_m
                    for _,lat,lon in vertices):
                return
            graph.add_way(str(way.id), vertices, tags)

    Loader().apply_file(path, locations=True, idx="flex_mem")
    return graph
