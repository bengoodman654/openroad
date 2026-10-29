"""Tiny, immutable, date-specific city snapshot cache generated OFF-HOST.

A signed API may later read these source-pinned gzip/JSON packages with low
CPU/memory. No pickle or arbitrary Python object loading. No live deployment.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

from pilot.gtfs_engine import Connection,Snapshot,Stop

MAX_COMPRESSED=30*1024*1024
MAX_EXPANDED=100*1024*1024
MAX_STOPS=5000
MAX_TRIPS=30000
MAX_CONNECTIONS=200000
SCHEMA="openroad-city-snapshot-1"


def encode_city_snapshot(snapshot:Snapshot, destination:Path) ->dict:
    if not isinstance(snapshot,Snapshot) or not snapshot.connections:
        raise ValueError("No source-pinned connected GTFS city snapshot")
    payload={
        "schema":SCHEMA,
        "region":snapshot.region,
        "city":snapshot.city,
        "serviceDate":snapshot.service_day.isoformat(),
        "feedVersion":snapshot.feed_version,
        "sourceArchiveSha256":snapshot.source_sha256,
        "activeServiceCount":snapshot.active_service_count,
        "localTripCount":snapshot.local_trip_count,
        "invalidTimeRows":snapshot.invalid_time_rows,
        "stops":{k:asdict(v) for k,v in snapshot.stops.items()},
        "routes":snapshot.routes,
        "trips":snapshot.trips,
        "connections":[asdict(c) for c in snapshot.connections],
        "researchOnly":True,"selectable":False,
    }
    raw=json.dumps(payload,sort_keys=True,
                   separators=(",",":"),allow_nan=False).encode()
    if len(raw)>MAX_EXPANDED:
        raise ValueError("City timetable too large for safe research publication")
    blob=gzip.compress(raw,compresslevel=7,mtime=0)
    if len(blob)>MAX_COMPRESSED:
        raise ValueError("City package too large for private hosting")
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        raise ValueError("Never overwrite a published city schedule package")
    staged=destination.with_name(destination.name+".incomplete")
    if staged.exists():
        raise ValueError("Another snapshot build is incomplete")
    try:
        with staged.open("xb") as out:
            out.write(blob)
            out.flush()
            os.fsync(out.fileno())
        os.replace(staged,destination)
        return {"format":SCHEMA,"region":snapshot.region,
                "serviceDate":snapshot.service_day.isoformat(),
                "sourceArchiveSha256":snapshot.source_sha256,
                "packageSha256":hashlib.sha256(blob).hexdigest(),
                "compressedBytes":len(blob),
                "uncompressedBytes":len(raw),
                "connections":len(snapshot.connections),
                "stops":len(snapshot.stops),
                "researchOnly":True}
    finally:
        try:staged.unlink()
        except FileNotFoundError:pass


def load_city_cache(path,region,expected_source,service_date:date,
                    expected_package_sha:str) -> Snapshot:
    path=Path(path)
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=MAX_COMPRESSED:
        raise ValueError("Unsupported GTFS snapshot package")
    if not isinstance(expected_package_sha,str) or len(expected_package_sha)!=64:
        raise ValueError("Pinned package SHA is required")
    sha=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(65536),b""):
            sha.update(block)
    if sha.hexdigest()!=expected_package_sha:
        raise ValueError("City package bytes differ from trusted signed manifest")
    with gzip.open(path,"rb") as stream:
        raw=stream.read(MAX_EXPANDED+1)
        if len(raw)>MAX_EXPANDED:
            raise ValueError("Compressed timetable expanded beyond memory cap")
        if stream.read(1):
            raise ValueError("Unexpected extra data after city snapshot")
    data=json.loads(raw)
    if (not isinstance(data,dict) or data.get("schema")!=SCHEMA or
        data.get("researchOnly") is not True or
        data.get("selectable") is not False or
        data.get("region")!=region or
        data.get("sourceArchiveSha256")!=expected_source or
        data.get("serviceDate")!=service_date.isoformat()):
        raise ValueError("Wrong region, day or GTFS source digest")
    raw_stops=data.get("stops")
    raw_routes=data.get("routes")
    raw_trips=data.get("trips")
    raw_connections=data.get("connections")
    if (not isinstance(raw_stops,dict) or not 0<len(raw_stops)<=MAX_STOPS or
        not isinstance(raw_routes,dict) or
        not isinstance(raw_trips,dict) or len(raw_trips)>MAX_TRIPS or
        not isinstance(raw_connections,list) or
        not 0<len(raw_connections)<=MAX_CONNECTIONS):
        raise ValueError("Malformed or unbounded research timetable tables")
    stops={}
    for k,v in raw_stops.items():
        if not isinstance(k,str) or not isinstance(v,dict) or v.get("id")!=k:
            raise ValueError("Invalid GTFS stop key")
        stop=Stop(**v)
        if not math.isfinite(stop.lat) or not math.isfinite(stop.lon) or (
                abs(stop.lat)>90 or abs(stop.lon)>180):
            raise ValueError("Invalid GTFS stop location")
        stops[k]=stop
    routes={}
    for k,v in raw_routes.items():
        if not isinstance(k,str) or not isinstance(v,list) or len(v)!=2:
            raise ValueError("Invalid bus route metadata")
        routes[k]=tuple(v)
    trips={}
    for k,v in raw_trips.items():
        if (not isinstance(k,str) or not isinstance(v,list) or
            len(v)!=2 or v[0] not in routes):
            raise ValueError("Unrecognised bus route on trip")
        trips[k]=tuple(v)
    conns=[]
    last=-1
    for v in raw_connections:
        if not isinstance(v,dict):raise ValueError("Malformed stop connection")
        c=Connection(**v)
        if (c.trip not in trips or c.a not in stops or c.b not in stops or
            type(c.pickup) is not bool or type(c.dropoff) is not bool or
            type(c.depart) is not int or type(c.arrive) is not int or
            c.depart<0 or c.depart>259200 or
            c.arrive<c.depart or c.arrive>259200 or c.depart<last or
            type(c.from_sequence) is not int or
            type(c.to_sequence) is not int or
            c.to_sequence<=c.from_sequence):
            raise ValueError("GTFS stop sequence or schedule is invalid")
        conns.append(c)
        last=c.depart
    return Snapshot(
        city=str(data["city"]),region=region,service_day=service_date,
        feed_version=str(data["feedVersion"]),stops=stops,
        routes=routes,trips=trips,connections=conns,
        active_service_count=int(data["activeServiceCount"]),
        local_trip_count=int(data["localTripCount"]),
        source_sha256=expected_source,
        invalid_time_rows=int(data["invalidTimeRows"]))
