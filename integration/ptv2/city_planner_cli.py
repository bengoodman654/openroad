#!/usr/bin/env python3
"""OpenRoad isolated research planner CLI, not a public HTTP endpoint.

Signed PHP v2 worker is responsible for authentication, task ownership,
cancellation and process count. The CLI accepts one small JSON query on stdin.
All timetable source paths and source SHA are supplied by trusted server
configuration, never by the phone. Outputs are scheduled research-only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import resource
import sys
from pathlib import Path

# Locate only the adjacent, source-controlled library tree; no user-provided
# Python import path is trusted by this process.
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

class SourceMismatch(RuntimeError):
    pass

from maintenance.gtfs_refresh.connection_snapshot import (
    load_city_snapshot,CitySnapshotBudgetExceeded,CitySnapshotCancelled)
from maintenance.gtfs_refresh.coordinate_journeys import coordinate_journeys

sys.dont_write_bytecode=True
MAX_STDIN_BYTES=4096
MAX_STDOUT_BYTES=128*1024
SOURCE_REGIONS={"south_west":"Bristol","west_midlands":"Coventry"}


def _point(value):
    if not isinstance(value,dict) or set(value)!={"lat","lon"}:
        raise ValueError("Invalid point")
    lat,lon=value["lat"],value["lon"]
    if (type(lat) not in (int,float) or type(lon) not in (int,float) or
            not math.isfinite(lat) or not math.isfinite(lon) or
            abs(lat)>90 or abs(lon)>180):
        raise ValueError("Invalid point")
    return (float(lat),float(lon))


def validate_request(request):
    if not isinstance(request,dict) or set(request)!={
            "from","to","serviceDate","earliestSec","maxWalkMetres"}:
        raise ValueError("Unexpected research request fields")
    origin=_point(request["from"])
    destination=_point(request["to"])
    date=dt.date.fromisoformat(request["serviceDate"])
    sec=request["earliestSec"]
    walk=request["maxWalkMetres"]
    if type(sec) is not int or sec<0 or sec>172800:
        raise ValueError("Unsupported service time")
    if type(walk) is not int or not 50<=walk<=1800:
        raise ValueError("Invalid walking limit")
    return origin,destination,date,sec,walk


def run_source(index,region,expected_sha,request):
    if region not in SOURCE_REGIONS:
        raise ValueError("Unsupported timetable region")
    if not isinstance(expected_sha,str) or len(expected_sha)!=64 or any(
            ch not in "0123456789abcdef" for ch in expected_sha):
        raise ValueError("Invalid pinned source digest")
    origin,destination,service_date,seconds,walk=validate_request(request)
    snapshot=load_city_snapshot(index,region,SOURCE_REGIONS[region],
         service_date,origin,destination,radius_m=2200,budget_s=7)
    if snapshot.source_sha256!=expected_sha:
        raise SourceMismatch("Index source digest changed")
    return coordinate_journeys(snapshot,origin,destination,
                seconds,max_walk_m=walk,max_nearby=5,
                max_pairs=25,max_results=3,budget_s=6)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--index",required=True)
    parser.add_argument("--region",required=True,choices=tuple(SOURCE_REGIONS))
    parser.add_argument("--source-sha",required=True)
    a=parser.parse_args()
    try:
        # Ceiling on the per-worker memory/CPU budget, not a system-wide limit.
        # 384 MB covers the bounded in-memory city connection graph.
        resource.setrlimit(resource.RLIMIT_AS,(384*1024*1024,384*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(10,11))
        data=sys.stdin.buffer.read(MAX_STDIN_BYTES+1)
        if len(data)>MAX_STDIN_BYTES:
            raise ValueError("Input too large")
        request=json.loads(data.decode("utf-8"))
        result=run_source(a.index,a.region,a.source_sha,request)
    except (ValueError,TypeError,UnicodeError,json.JSONDecodeError):
        result={"outcome":"INPUT_INVALID","researchOnly":True,"results":[]}
    except (CitySnapshotBudgetExceeded,TimeoutError):
        result={"outcome":"SEARCH_LIMIT","reasonCode":"SOURCE_LOAD_BUDGET",
                "researchOnly":True,"results":[]}
    except CitySnapshotCancelled:
        result={"outcome":"CANCELLED","researchOnly":True,"results":[]}
    except BaseException:
        # Full private filesystem and transport keys must never be returned
        # to an Android client or logged on stdout.
        result={"outcome":"PROVIDER_UNAVAILABLE","researchOnly":True,"results":[]}
    blob=json.dumps(result,separators=(",",":"),allow_nan=False).encode()
    if len(blob)>MAX_STDOUT_BYTES:
        blob=b'{"outcome":"SEARCH_LIMIT","researchOnly":true,"results":[]}'
    sys.stdout.buffer.write(blob+b"\n")


if __name__=="__main__":
    main()
