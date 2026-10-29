"""Isolated OpenRoad public-transport GTFS research engine.

Purpose: prove date-valid, stop-to-stop *scheduled bus* paths in a limited
Bristol/Coventry pilot, away from production. This is not an Android/server
integration, realtime engine, a walking-path router, or accessibility proof.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_left, bisect_right
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
import time
from collections import defaultdict
from zoneinfo import ZoneInfo
from zipfile import ZipFile

CENTRES = {
    "Coventry": (52.4081, -1.5106),
    "Bristol": (51.4545, -2.5879),
}
REQUIRED = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}


def gtfs_seconds(value: str) -> int:
    """Elapsed seconds from GTFS service-day anchor; hours may exceed 23."""
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid GTFS time")
    h, m, s = map(int, parts)
    if not (0 <= h <= 71 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError("Invalid GTFS time range")
    return 3600 * h + 60 * m + s


def gtfs_utc(service_day: date, seconds: int, tz: str = "Europe/London") -> datetime:
    """GTFS noon-minus-12h anchor; handles DST as elapsed instants."""
    noon = datetime(service_day.year, service_day.month, service_day.day,
                    12, tzinfo=ZoneInfo(tz))
    anchor = noon.astimezone(timezone.utc) - timedelta(hours=12)
    return anchor + timedelta(seconds=seconds)


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    dl = math.radians(lat2 - lat1)
    dn = math.radians(lon2 - lon1)
    s = (math.sin(dl/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dn/2)**2)
    return 12742000 * math.asin(min(1.0, math.sqrt(s)))


def rows(z: ZipFile, filename: str):
    if filename not in z.namelist():
        return
    with z.open(filename) as stream:
        yield from csv.DictReader(io.TextIOWrapper(
            stream, encoding="utf-8-sig", errors="replace", newline=""))


def active_services(z: ZipFile, service_day: date) -> set[str]:
    day = service_day.strftime("%Y%m%d")
    weekday = service_day.strftime("%A").lower()
    active = set()
    for row in rows(z, "calendar.txt"):
        if row.get("start_date", "") <= day <= row.get("end_date", "") and row.get(weekday) == "1":
            active.add(row["service_id"])
    for row in rows(z, "calendar_dates.txt"):
        if row.get("date") != day:
            continue
        if row.get("exception_type") == "1":
            active.add(row["service_id"])
        elif row.get("exception_type") == "2":
            active.discard(row["service_id"])
    return active


@dataclass(frozen=True, slots=True)
class Stop:
    id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Connection:
    trip: str
    a: str
    b: str
    depart: int
    arrive: int
    pickup: bool
    dropoff: bool
    from_sequence: int = 0
    to_sequence: int = 0


@dataclass(slots=True)
class Snapshot:
    city: str
    region: str
    service_day: date
    feed_version: str
    stops: dict[str, Stop]
    routes: dict[str, tuple[str, str]]
    trips: dict[str, tuple[str, str]]
    connections: list[Connection]
    active_service_count: int
    local_trip_count: int
    source_sha256: str
    invalid_time_rows: int

    def summary(self) -> dict:
        return {
            "city": self.city, "region": self.region,
            "serviceDate": str(self.service_day),
            "feedVersion": self.feed_version,
            "sourceSHA256": self.source_sha256,
            "stops": len(self.stops),
            "activeServices": self.active_service_count,
            "localTrips": self.local_trip_count,
            "connections": len(self.connections),
            "invalidTimeRows": self.invalid_time_rows,
            "status": "RESEARCH_ONLY_NOT_RELEASE_READY",
        }


def source_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_region(path: str, city: str, region: str, service_day: date,
                radius_m: int = 15000, sha256: str | None = None) -> Snapshot:
    """Stream official GTFS ZIP, retaining only date-valid nearby bus segments.

    The area clipping deliberately omits any segment leaving/re-entering the
    radius. It MUST NOT be described as a national/cross-region router.
    """
    if city not in CENTRES:
        raise ValueError("Unsupported pilot city")
    with ZipFile(path) as z:
        if not REQUIRED.issubset(z.namelist()) or not (
                "calendar.txt" in z.namelist() or "calendar_dates.txt" in z.namelist()):
            raise ValueError("Missing required GTFS files")
        feed = next(rows(z, "feed_info.txt"), {})
        feed_start, feed_end = feed.get("feed_start_date"), feed.get("feed_end_date")
        ymd = service_day.strftime("%Y%m%d")
        if feed_start and feed_end and not (feed_start <= ymd <= feed_end):
            raise ValueError("COVERAGE_MISSING: outside feed date range")
        centre = CENTRES[city]
        stops = {}
        for row in rows(z, "stops.txt"):
            try:
                lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                if distance_m((lat, lon), centre) <= radius_m:
                    stops[row["stop_id"]] = Stop(
                        row["stop_id"], row.get("stop_name", ""), lat, lon)
            except (KeyError, ValueError, TypeError):
                continue
        services = active_services(z, service_day)
        routes = {row["route_id"]: (
            row.get("route_short_name") or row.get("route_long_name", ""),
            row.get("agency_id", "")) for row in rows(z, "routes.txt")
            if row.get("route_type") == "3"}
        trips = {row["trip_id"]: (
            row["route_id"], row["service_id"])
            for row in rows(z, "trips.txt")
            if row.get("service_id") in services and row.get("route_id") in routes}
        # Stops and trips may carry *the same public bus number* across agencies.
        # Never key route identity on route_short_name.
        by_trip = defaultdict(list)
        # GTFS stop_sequence values need only increase: 10, 20, 30 is
        # legitimate. Retain ALL event sequence IDs for eligible services,
        # including stops outside the pilot radius, to detect real adjacency.
        # Unsigned arrays bound memory while streaming large regional feeds.
        full_sequences = defaultdict(lambda: array("I"))
        invalid_times = 0
        for row in rows(z, "stop_times.txt"):
            trip, stop = row.get("trip_id"), row.get("stop_id")
            if trip not in trips:
                continue
            try:
                seq = int(row["stop_sequence"])
                if not 0 <= seq < 2**32:
                    raise ValueError("Invalid stop_sequence")
                full_sequences[trip].append(seq)
            except (ValueError, KeyError, TypeError):
                invalid_times += 1
                continue
            if stop not in stops:
                continue
            try:
                arr = gtfs_seconds(row["arrival_time"])
                dep = gtfs_seconds(row["departure_time"])
                if dep < arr:
                    invalid_times += 1
                    continue
            except (ValueError, KeyError, TypeError):
                invalid_times += 1
                continue
            by_trip[trip].append((
                seq, stop, arr, dep,
                row.get("pickup_type", "0") not in ("1", "2", "3"),
                row.get("drop_off_type", "0") not in ("1", "2", "3"),
            ))
        connections = []
        for trip_id, stop_events in by_trip.items():
            stop_events.sort()
            all_seqs = sorted(full_sequences[trip_id])
            for a, b in zip(stop_events, stop_events[1:]):
                ia = bisect_left(all_seqs, a[0])
                ja = bisect_right(all_seqs, a[0])
                ib = bisect_left(all_seqs, b[0])
                jb = bisect_right(all_seqs, b[0])
                # Exactly one occurrence of each event and NO intervening
                # event (even one outside the radius). Avoid fabricated legs.
                if (a[0] >= b[0] or ja-ia != 1 or jb-ib != 1 or
                        ja != ib or b[2] < a[3]):
                    continue
                connections.append(Connection(
                    trip_id, a[1], b[1], a[3], b[2],
                    a[4], b[5], a[0], b[0]))
        connections.sort(key=lambda x: (x.depart, x.arrive, x.trip, x.a, x.b))
        local_trips = {x.trip for x in connections}
        trips = {k:v for k,v in trips.items() if k in local_trips}
        return Snapshot(
            city, region, service_day, feed.get("feed_version", ""),
            stops, routes, trips, connections,
            len(services), len(by_trip), sha256 or source_hash(path), invalid_times)


@dataclass(slots=True)
class Path:
    previous: "Path | None"
    mode: str
    a: str
    b: str
    depart: int
    arrive: int
    trip: str | None
    transfers: int
    walked_m: int


def _path(result: Path | None, s: Snapshot) -> list[dict]:
    legs = []
    while result is not None and result.previous is not None:
        leg = {
            "mode": result.mode,
            "from": result.a,
            "fromName": s.stops[result.a].name,
            "to": result.b,
            "toName": s.stops[result.b].name,
            "depart": result.depart,
            "arrive": result.arrive,
        }
        if result.trip:
            route, service = s.trips[result.trip]
            leg.update(tripOccurrence=f"{s.region}:{result.trip}:{s.service_day}",
                       publicLine=s.routes[route][0],
                       routeKey=f"{s.region}:{route}")
        legs.append(leg)
        result = result.previous
    legs.reverse()
    # Merge consecutive connection segments for a single boarded trip.
    merged = []
    for leg in legs:
        if (merged and leg["mode"] == merged[-1]["mode"] == "BUS" and
                leg.get("tripOccurrence") == merged[-1].get("tripOccurrence") and
                merged[-1]["to"] == leg["from"]):
            merged[-1]["to"] = leg["to"]
            merged[-1]["toName"] = leg["toName"]
            merged[-1]["arrive"] = leg["arrive"]
        else:
            merged.append(leg)
    return merged


def plan_stops(s: Snapshot, origin: str, destination: str, start_sec: int,
               transfer_seconds: int = 120, max_transfers: int = 3) -> dict:
    """One-earliest-arrival connection scan for *exact* stop IDs.

    No walking/accessible-path claims. Does not generate Pareto alternatives.
    A bounded baseline for deterministic proof, NOT a full release router.
    """
    if origin not in s.stops or destination not in s.stops:
        return {"outcome": "COVERAGE_MISSING", "reasonCode": "STOP_OUTSIDE_PILOT_AREA"}
    if origin == destination:
        return {"outcome": "OK", "legs": [], "arrival": start_sec}
    if not s.connections:
        return {"outcome": "COVERAGE_MISSING", "reasonCode": "NO_VALID_GRAPH"}
    root = Path(None, "START", origin, origin, start_sec, start_sec,
                None, 0, 0)
    best = {origin: (start_sec, root)}
    onboard = {}
    for con in s.connections:
        if con.depart < start_sec:
            continue
        prior = best.get(con.a)
        candidate = None
        if prior and con.pickup:
            arr_at_stop, path = prior
            # No minimum interchange at the initial origin.
            change_buffer = 0 if path.previous is None else transfer_seconds
            if arr_at_stop + change_buffer <= con.depart:
                changes = path.transfers + (
                    1 if path.trip is not None and path.trip != con.trip else 0)
                if changes <= max_transfers:
                    candidate = (path, changes)
        staying = onboard.get(con.trip)
        if staying and staying.b == con.a:
            if candidate is None or staying.transfers <= candidate[1]:
                candidate = (staying, staying.transfers)
        if candidate is None:
            continue
        previous, changes = candidate
        link = Path(previous, "BUS", con.a, con.b, con.depart,
                    con.arrive, con.trip, changes, previous.walked_m)
        # Boarding/alighting rules apply independently; riding through a
        # no-dropoff stop still keeps this trip eligible for the next segment.
        onboard[con.trip] = link
        current = best.get(con.b)
        if con.dropoff and (current is None or con.arrive < current[0]):
            best[con.b] = (con.arrive, link)
    if destination not in best:
        return {
            "outcome": "NO_JOURNEY",
            "reasonCode": "NO_FEASIBLE_SCHEDULED_CONNECTION",
            "results": [],
        }
    arrival, result = best[destination]
    legs = _path(result, s)
    return {
        "outcome": "OK", "serviceDate": str(s.service_day),
        "snapshot": s.source_sha256[:16],
        "departAfter": start_sec, "arrival": arrival,
        "legs": legs,
        "transfers": max(0, len([l for l in legs if l["mode"] == "BUS"]) - 1),
        "warnings": ["SCHEDULED_ONLY", "RESEARCH_ENGINE_NO_WALKING_GRAPH"],
    }



def plan_coordinates(s: Snapshot, origin: tuple[float,float],
                     destination: tuple[float,float], start_sec: int,
                     max_total_walk_m: int = 800,
                     candidate_stops: int = 4) -> dict:
    """Experimental first/last-mile stop selection, NOT pedestrian routing.

    Straight-line distance with a detour factor provides only an estimate.
    Do not enable strict accessibility or production walking guidance from it.
    """
    def options(point):
        choices=[]
        for stop in s.stops.values():
            metres=math.ceil(distance_m(point,(stop.lat,stop.lon))*1.4)
            if metres <= max_total_walk_m:
                choices.append((metres,stop.id))
        return sorted(choices)[:candidate_stops]
    origins=options(origin)
    targets=options(destination)
    if not origins or not targets:
        return {"outcome":"NO_JOURNEY","reasonCode":"WALKING_LIMIT"}
    winning=None
    for metres_a,a in origins:
        walk_a=math.ceil(metres_a/1.25)
        for metres_b,b in targets:
            if metres_a+metres_b>max_total_walk_m or a==b:
                continue
            result=plan_stops(s,a,b,start_sec+walk_a)
            if result["outcome"]!="OK":
                continue
            finish=result["arrival"]+math.ceil(metres_b/1.25)
            score=(finish,metres_a+metres_b,result["transfers"])
            if winning is None or score<winning[0]:
                winning=(score,result,metres_a,metres_b,a,b)
    if winning is None:
        return {"outcome":"NO_JOURNEY","reasonCode":"NO_FEASIBLE_SCHEDULED_CONNECTION"}
    score,result,metres_a,metres_b,a,b=winning
    legs=[]
    if metres_a:
        legs.append({"mode":"WALK_ESTIMATE","to":a,
                     "toName":s.stops[a].name,"metres":metres_a,
                     "geometryValidated":False})
    legs.extend(result["legs"])
    if metres_b:
        legs.append({"mode":"WALK_ESTIMATE","from":b,
                     "fromName":s.stops[b].name,"metres":metres_b,
                     "geometryValidated":False})
    return {
        **result,"arrival":score[0],"legs":legs,
        "estimatedWalkingMetres":metres_a+metres_b,
        "warnings":["SCHEDULED_ONLY","UNVERIFIED_STRAIGHT_LINE_WALKING",
                    "NO_ACCESSIBILITY_PROOF"],
    }



def populate_sqlite(s: Snapshot, db) -> None:
    """Create compact per-service-day serving index in supplied SQLite DB.

    Only opaque INTEGER surrogate keys are repeated in dense connections.
    Build on an OFF-HOST worker, never during an Android query. Production
    deployment still requires measured RAM/disk/query-safety gates.
    """
    db.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_key INTEGER PRIMARY KEY,
            content_sha256 TEXT NOT NULL,
            city TEXT NOT NULL,
            service_date TEXT NOT NULL,
            feed_version TEXT NOT NULL,
            UNIQUE(content_sha256,city,service_date));
        CREATE TABLE IF NOT EXISTS stops (
            stop_key INTEGER PRIMARY KEY,
            snapshot_key INTEGER NOT NULL,
            source_stop_id TEXT NOT NULL,
            name TEXT, latitude REAL, longitude REAL,
            UNIQUE(snapshot_key,source_stop_id));
        CREATE TABLE IF NOT EXISTS routes (
            route_key INTEGER PRIMARY KEY,
            snapshot_key INTEGER NOT NULL,
            source_route_id TEXT NOT NULL,
            public_line TEXT, agency_id TEXT,
            UNIQUE(snapshot_key,source_route_id));
        CREATE TABLE IF NOT EXISTS trips (
            trip_key INTEGER PRIMARY KEY,
            snapshot_key INTEGER NOT NULL,
            source_trip_id TEXT NOT NULL,
            route_key INTEGER NOT NULL,
            service_id TEXT NOT NULL,
            UNIQUE(snapshot_key,source_trip_id));
        CREATE TABLE IF NOT EXISTS connections (
            snapshot_key INTEGER NOT NULL, trip_key INTEGER NOT NULL,
            from_stop_key INTEGER NOT NULL, to_stop_key INTEGER NOT NULL,
            depart INTEGER NOT NULL, arrive INTEGER NOT NULL,
            flags INTEGER NOT NULL,
            from_sequence INTEGER NOT NULL, to_sequence INTEGER NOT NULL);
    """)
    release=(s.source_sha256,s.city,str(s.service_day))
    if db.execute("""SELECT 1 FROM snapshots
                   WHERE content_sha256=? AND city=? AND service_date=?""",
                   release).fetchone():
        raise ValueError("Duplicate immutable snapshot ID")
    with db:
        cur=db.execute("""INSERT INTO snapshots
                          (content_sha256,city,service_date,feed_version)
                          VALUES(?,?,?,?)""",(*release,s.feed_version))
        sid=cur.lastrowid
        db.executemany("""INSERT INTO stops
                          (snapshot_key,source_stop_id,name,latitude,longitude)
                          VALUES(?,?,?,?,?)""",
                       ((sid,x.id,x.name,x.lat,x.lon) for x in s.stops.values()))
        stop_keys={external:key for key,external in db.execute(
            "SELECT stop_key,source_stop_id FROM stops WHERE snapshot_key=?",(sid,))}
        db.executemany("""INSERT INTO routes
                          (snapshot_key,source_route_id,public_line,agency_id)
                          VALUES(?,?,?,?)""",
                       ((sid,k,v[0],v[1]) for k,v in s.routes.items()))
        route_keys={external:key for key,external in db.execute(
            "SELECT route_key,source_route_id FROM routes WHERE snapshot_key=?",(sid,))}
        db.executemany("""INSERT INTO trips
                          (snapshot_key,source_trip_id,route_key,service_id)
                          VALUES(?,?,?,?)""",
                       ((sid,k,route_keys[v[0]],v[1]) for k,v in s.trips.items()))
        trip_keys={external:key for key,external in db.execute(
            "SELECT trip_key,source_trip_id FROM trips WHERE snapshot_key=?",(sid,))}
        db.executemany("""INSERT INTO connections
                          (snapshot_key,trip_key,from_stop_key,to_stop_key,
                           depart,arrive,flags,from_sequence,to_sequence)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       ((sid,trip_keys[x.trip],stop_keys[x.a],stop_keys[x.b],
                         x.depart,x.arrive,int(x.pickup)|int(x.dropoff)<<1,
                         x.from_sequence,x.to_sequence)
                        for x in s.connections))
        db.execute("CREATE INDEX IF NOT EXISTS idx_connections_depart "
                   "ON connections(snapshot_key,depart,trip_key)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_connections_stop "
                   "ON connections(snapshot_key,from_stop_key,depart)")


def select_real_case(s: Snapshot) -> dict:
    """Choose reproducibly one published trip with 7+ contiguous local stops."""
    events = defaultdict(list)
    for con in s.connections:
        events[con.trip].append(con)
    candidates = []
    centre = CENTRES[s.city]
    for trip, legs in events.items():
        if len(legs) < 6:
            continue
        legs.sort(key=lambda x: x.depart)
        for i in range(len(legs) - 5):
            chunk = legs[i:i+6]
            if any(chunk[j].b != chunk[j+1].a for j in range(5)):
                continue
            first, last = chunk[0], chunk[-1]
            if not (36000 <= first.depart <= 54000 and
                    600 <= last.arrive-first.depart <= 3600):
                continue
            if distance_m((s.stops[first.a].lat,s.stops[first.a].lon),centre)>6500:
                continue
            if distance_m((s.stops[last.b].lat,s.stops[last.b].lon),centre)>6500:
                continue
            route_id = s.trips[trip][0]
            line = s.routes[route_id][0]
            candidates.append((first.depart, line, trip, first.a, last.b, last.arrive))
            break
    if not candidates:
        raise RuntimeError("No real case: valid local same-trip journey unavailable")
    # First deterministic candidate after 10am, with defined source trip IDs.
    dep,line,trip,a,b,arr = sorted(candidates)[0]
    result = plan_stops(s, a, b, dep-300)
    if result["outcome"] != "OK":
        raise AssertionError("Real published trip not routable")
    if result["arrival"] > arr:
        raise AssertionError("Real routing worse than known feasible published trip")
    return {
        "city": s.city,
        "sourceTrip": f"{s.region}:{trip}:{s.service_day}",
        "publicLine": line,
        "startStop": a, "startName": s.stops[a].name,
        "endStop": b, "endName": s.stops[b].name,
        "publishedDepartureSec": dep, "publishedArrivalSec": arr,
        "computedArrivalSec": result["arrival"],
        "computedLegs": result["legs"],
        "oracle": "Routed arrival no later than published feasible direct trip",
        "status": "PASS_RESEARCH_NOT_PRODUCTION",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--west", required=True)
    parser.add_argument("--south", required=True)
    parser.add_argument("--date", default="2026-10-26")
    args = parser.parse_args(argv)
    d = date.fromisoformat(args.date)
    for city, region, path in [
        ("Coventry", "west_midlands", args.west),
        ("Bristol", "south_west", args.south),
    ]:
        t0=time.monotonic()
        snapshot = load_region(path, city, region, d)
        print(json.dumps({
            "inventory":snapshot.summary(),
            "realCase":select_real_case(snapshot),
            "elapsedSeconds":round(time.monotonic()-t0, 2),
        }),flush=True)


if __name__ == "__main__":
    main()
