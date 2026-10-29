"""Off-host bounded SQLite -> scheduled city connection-scan snapshot.

Bridge the fresh indexed BODS timetable to the already-tested v2 connection
scan with up to two transfers. This is RESEARCH ONLY: the trip plan is not
a navigable Android result and is not deployed to the shared PHP host.
"""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
import sqlite3
import time

from pilot.gtfs_engine import Connection, Snapshot, Stop, distance_m


class CitySnapshotBudgetExceeded(RuntimeError):
    pass


class CitySnapshotCancelled(RuntimeError):
    pass


def load_city_snapshot(index_path, region: str, city: str, service_date: date,
                       origin: tuple[float,float],
                       destination: tuple[float,float],
                       radius_m: int = 3800, budget_s: float = 8.0,
                       cancel=lambda: False,
                       max_stops: int = 3500,
                       max_trips: int = 18000,
                       max_calls: int = 450000) -> Snapshot:
    """Load only actual GTFS stop-call adjacencies for an active service date.

    No invented edges across skipped out-of-area calls. Full scheduled trip
    sequences are checked before clipping to the local city network.
    """
    if not isinstance(service_date,date) or region not in ("south_west","west_midlands"):
        raise ValueError("Invalid dated regional timetable request")
    if not all(math.isfinite(x) for pt in (origin,destination) for x in pt):
        raise ValueError("Invalid route endpoints")
    if not 500 <= radius_m <= 10000 or budget_s <= 0 or budget_s > 30:
        raise ValueError("Unsupported city source query limits")
    if max_stops > 5000 or max_trips > 30000 or max_calls > 700000:
        raise ValueError("Unbounded GTFS city query")
    started = time.monotonic()
    def check():
        if cancel():
            raise CitySnapshotCancelled()
        if time.monotonic()-started > budget_s:
            raise CitySnapshotBudgetExceeded()
    filename=Path(index_path).resolve()
    if not filename.is_file():
        raise ValueError("GTFS index file missing")
    db=sqlite3.connect(filename.as_uri()+"?mode=ro&immutable=1",
                       uri=True,timeout=0.4)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    interrupted=None
    def progress():
        nonlocal interrupted
        if cancel():
            interrupted="cancel"
            return 1
        if time.monotonic()-started > budget_s:
            interrupted="budget"
            return 1
        return 0
    db.set_progress_handler(progress,1000)
    try:
        info={r["name"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM info")}
        if info.get("region")!=region or info.get("schema") not in (
            "openroad-bus-sqlite-1","openroad-bus-sqlite-compact-2"):
            raise ValueError("GTFS snapshot does not match requested region")
        source=info.get("sourceArchiveSha256")
        if not isinstance(source,str) or len(source)!=64:
            raise ValueError("Unpinned regional timetable source")
        active={r[0] for r in db.execute(
            "SELECT service_id FROM service_days WHERE date=?",
            (service_date.isoformat(),))}
        if not active:
            raise ValueError("No source calendar on requested date")
        # Query a bounding rectangle first, then filter strictly by distance
        # to origin OR destination. This avoids a city-wide table scan per stop.
        lat_margin=radius_m/111200.0
        west=min(origin[1],destination[1])
        east=max(origin[1],destination[1])
        south=min(origin[0],destination[0])
        north=max(origin[0],destination[0])
        cos=max(.3,math.cos(math.radians((south+north)/2)))
        lon_margin=radius_m/(111200.0*cos)
        candidates=db.execute(
            "SELECT stop_id,name,lat,lon FROM stops "
            "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
            (south-lat_margin,north+lat_margin,
             west-lon_margin,east+lon_margin))
        local={}
        for i,r in enumerate(candidates):
            if i%100==0:check()
            point=(r["lat"],r["lon"])
            if min(distance_m(point,origin),distance_m(point,destination))<=radius_m:
                local[r["stop_id"]]=Stop(r["stop_id"],r["name"],
                                         r["lat"],r["lon"])
                if len(local)>max_stops:
                    raise CitySnapshotBudgetExceeded("Stop count cap reached")
        if not local:
            raise ValueError("No prepared stops within city scope")
        matched_trips=set()
        # All local calls are looked up via the indexed stop_id; trip IDs
        # are bounded before reading any full stop_time records.
        for index,stop in enumerate(sorted(local)):
            if index%32==0:check()
            for r in db.execute(
                "SELECT s.trip_id FROM stop_times s "
                "JOIN trips t ON t.trip_id=s.trip_id "
                "JOIN routes r ON r.route_id=t.route_id "
                "JOIN service_days d ON d.service_id=t.service_id AND d.date=? "
                "WHERE s.stop_id=? AND "
                "(r.route_type=3 OR r.route_type BETWEEN 700 AND 799)",
                (service_date.isoformat(),stop)):
                matched_trips.add(r["trip_id"])
                if len(matched_trips)>max_trips:
                    raise CitySnapshotBudgetExceeded("Active trip count cap reached")
        routes={}
        trips={}
        conns=[]
        invalid=0
        call_count=0
        ids=sorted(matched_trips)
        for offset in range(0,len(ids),150):
            check()
            part=ids[offset:offset+150]
            params=",".join("?" for _ in part)
            for t in db.execute(
                f"SELECT t.trip_id,t.route_id,t.headsign,r.short_name,r.long_name "
                f"FROM trips t JOIN routes r ON r.route_id=t.route_id "
                f"WHERE t.trip_id IN ({params})",part):
                routes[t["route_id"]]=(t["short_name"],t["long_name"])
                trips[t["trip_id"]]=(t["route_id"],t["headsign"])
            # Full actual stop sequence, including stops outside area,
            # prevents false adjacent edges across omitted service stops.
            previous={}
            for row in db.execute(
                f"SELECT trip_id,seq,stop_id,arrival_sec,departure_sec,"
                f"pickup,dropoff FROM stop_times "
                f"WHERE trip_id IN ({params}) ORDER BY trip_id,seq",part):
                call_count+=1
                if call_count%1000==0:check()
                if call_count>max_calls:
                    raise CitySnapshotBudgetExceeded("Stop-time count cap reached")
                trip=row["trip_id"]
                before=previous.get(trip)
                if before is not None:
                    valid=(before["stop_id"] in local and
                           row["stop_id"] in local and
                           before["departure_sec"]<=row["arrival_sec"] and
                           row["arrival_sec"]>=0 and
                           before["departure_sec"]>=0)
                    if valid:
                        conns.append(Connection(
                            trip,before["stop_id"],row["stop_id"],
                            before["departure_sec"],row["arrival_sec"],
                            before["pickup"]==0,row["dropoff"]==0,
                            before["seq"],row["seq"]))
                    elif before["stop_id"] in local and row["stop_id"] in local:
                        invalid+=1
                previous[trip]=row
        check()
        conns.sort(key=lambda e:(e.depart,e.arrive,e.trip,
                                 e.from_sequence,e.to_sequence))
        return Snapshot(
            city=city,region=region,service_day=service_date,
            feed_version=str(info.get("createdOn") or "unknown"),
            stops=local,routes=routes,trips=trips,connections=conns,
            active_service_count=len(active),local_trip_count=len(trips),
            source_sha256=source,invalid_time_rows=invalid)
    except sqlite3.OperationalError as e:
        if interrupted=="cancel":
            raise CitySnapshotCancelled() from e
        if interrupted=="budget":
            raise CitySnapshotBudgetExceeded() from e
        raise
    finally:
        db.set_progress_handler(None,0)
        db.close()
