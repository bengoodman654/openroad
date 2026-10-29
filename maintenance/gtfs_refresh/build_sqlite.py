#!/usr/bin/env python3
"""Off-host SQLite timetable builder (research-only until route engine certified).

Consumes a validated official BODS GTFS ZIP, streaming the large stop_times
table; never connects to the live server or writes any user account data.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import zipfile
from maintenance.gtfs_refresh.validate_gtfs import (
    FeedRejected, safe_members, validate_archive,
)

MAX_STOP_TIMES=25000000
MAX_SHAPES=0   # Stop-time index only. No fabricated navigation geometry.
BATCH=8000

DDL = """
PRAGMA foreign_keys=OFF;
CREATE TABLE info (name TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE stops(stop_id TEXT PRIMARY KEY,name TEXT NOT NULL,
                   lat REAL NOT NULL,lon REAL NOT NULL);
CREATE TABLE routes(route_id TEXT PRIMARY KEY,short_name TEXT,long_name TEXT,
                    route_type INTEGER);
CREATE TABLE trips(trip_id TEXT PRIMARY KEY,route_id TEXT NOT NULL,
                   service_id TEXT NOT NULL,headsign TEXT,shape_id TEXT);
CREATE TABLE stop_times(trip_id TEXT NOT NULL,seq INTEGER NOT NULL,
                        stop_id TEXT NOT NULL,arrival_sec INTEGER NOT NULL,
                        departure_sec INTEGER NOT NULL,
                        pickup INTEGER NOT NULL,dropoff INTEGER NOT NULL,
                        PRIMARY KEY(trip_id,seq)) WITHOUT ROWID;
CREATE TABLE service_days(service_id TEXT NOT NULL,date TEXT NOT NULL,
                          PRIMARY KEY(date,service_id)) WITHOUT ROWID;
"""

def duration_seconds(text):
    if not re.fullmatch(r"\d{1,3}:\d{2}:\d{2}",text or ""):
        return None
    h,m,s=map(int,text.split(":"))
    if h>72 or m>59 or s>59:return None
    return h*3600+m*60+s

def walk_rows(z,member,required=()):
    with z.open(member) as fh:
        rdr=csv.DictReader(io.TextIOWrapper(fh,encoding="utf-8-sig",newline=""))
        if not set(required).issubset(set(rdr.fieldnames or ())):
            raise FeedRejected("Missing source columns")
        for r in rdr:
            yield r

def batch_insert(db,sql,iterable,batch=BATCH):
    buffer=[]
    n=0
    for x in iterable:
        if x is None:continue
        buffer.append(x)
        if len(buffer)>=batch:
            db.executemany(sql,buffer);n+=len(buffer);buffer.clear()
    if buffer:db.executemany(sql,buffer);n+=len(buffer)
    return n

def add_service_calendar(db,z,members,services,today,horizon=56):
    if not 7<=horizon<=90:raise FeedRejected("Calendar horizon unsafe")
    # Yesterday matters for GTFS departures at 24:xx or 26:xx after midnight.
    wanted=[today+dt.timedelta(days=i) for i in range(-1,horizon+1)]
    dates={d.strftime("%Y%m%d"):d for d in wanted}
    byday={d: set() for d in wanted}
    if "calendar.txt" in members:
        for r in walk_rows(z,members["calendar.txt"],
                           ("service_id","start_date","end_date")):
            service=r["service_id"]
            if service not in services:continue
            start,end=r["start_date"],r["end_date"]
            if not re.fullmatch(r"\d{8}",start) or not re.fullmatch(r"\d{8}",end):
                continue
            for key,d in dates.items():
                if start<=key<=end and r.get(d.strftime("%A").lower())=="1":
                    byday[d].add(service)
    if "calendar_dates.txt" in members:
        for r in walk_rows(z,members["calendar_dates.txt"],
                           ("service_id","date","exception_type")):
            s=r["service_id"]
            d=dates.get(r["date"])
            if s not in services or d is None:continue
            if r["exception_type"]=="1":byday[d].add(s)
            elif r["exception_type"]=="2":byday[d].discard(s)
    result=[(d.isoformat(),s) for d,v in byday.items() for s in v]
    if not result:raise FeedRejected("No active service days in range")
    db.executemany("INSERT INTO service_days(date,service_id) VALUES(?,?)",result)
    return len(result)

def build_index(source,region,out,today,skip_preflight=False):
    source=Path(source);out=Path(out)
    if not skip_preflight:
        verified=validate_archive(source,region,today)
    else:
        # Skip only the expensive preflight on a source already checked
        # in the same immutable GitHub job; not for live deployments.
        verified={"archiveSha256":_sha(source),"region":region}
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FeedRejected("Refuse to overwrite an existing published index")
    tmp=out.with_name(out.name+".incomplete")
    if tmp.exists():raise FeedRejected("Another incomplete index exists")
    db=None
    try:
        db=sqlite3.connect(tmp)
        db.executescript(DDL)
        # This database is never visible to server readers until fully
        # finalized and atomically renamed.
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA temp_store=FILE")
        with zipfile.ZipFile(source) as z:
            members=safe_members(z)
            def stops():
                for r in walk_rows(z,members["stops.txt"],
                                   ("stop_id","stop_name","stop_lat","stop_lon")):
                    try:yield(r["stop_id"],r["stop_name"],float(r["stop_lat"]),
                              float(r["stop_lon"]))
                    except (ValueError,TypeError):raise FeedRejected("Bad stop coordinates")
            nstops=batch_insert(db,
                "INSERT INTO stops VALUES(?,?,?,?)",stops())
            def routes():
                for r in walk_rows(z,members["routes.txt"],("route_id",)):
                    try:typ=int(r.get("route_type") or 3)
                    except ValueError:typ=3
                    yield(r["route_id"],r.get("route_short_name",""),
                          r.get("route_long_name",""),typ)
            nroutes=batch_insert(db,"INSERT INTO routes VALUES(?,?,?,?)",routes())
            services=set()
            def trips():
                for r in walk_rows(z,members["trips.txt"],
                                   ("trip_id","route_id","service_id")):
                    services.add(r["service_id"])
                    yield(r["trip_id"],r["route_id"],r["service_id"],
                          r.get("trip_headsign",""),r.get("shape_id",""))
            ntrips=batch_insert(db,"INSERT INTO trips VALUES(?,?,?,?,?)",trips())
            ndays=add_service_calendar(db,z,members,services,today)
            def stop_times():
                for ix,r in enumerate(walk_rows(
                        z,members["stop_times.txt"],
                        ("trip_id","stop_id","stop_sequence","arrival_time","departure_time"))):
                    if ix>=MAX_STOP_TIMES:raise FeedRejected("Oversized stop-time feed")
                    a=duration_seconds(r.get("arrival_time",""))
                    d=duration_seconds(r.get("departure_time",""))
                    if a is None:a=d
                    if d is None:d=a
                    if a is None or d is None:continue
                    try:seq=int(r["stop_sequence"])
                    except ValueError:raise FeedRejected("Invalid stop sequence")
                    pickup=int(r.get("pickup_type") or "0")
                    dropoff=int(r.get("drop_off_type") or "0")
                    yield(r["trip_id"],seq,r["stop_id"],a,d,pickup,dropoff)
            nstop_times=batch_insert(db,
                "INSERT INTO stop_times VALUES(?,?,?,?,?,?,?)",
                stop_times())
        if nstops<100 or nroutes<10 or ntrips<50 or nstop_times<50:
            raise FeedRejected("Incomplete regional timetable index")
        db.execute("CREATE INDEX idx_st_depart ON stop_times(stop_id,departure_sec,trip_id)")
        db.execute("CREATE INDEX idx_st_arrive ON stop_times(stop_id,arrival_sec,trip_id)")
        db.execute("CREATE INDEX idx_trip_service ON trips(service_id,trip_id)")
        db.execute("CREATE INDEX idx_stop_location ON stops(lat,lon)")
        db.execute("CREATE INDEX idx_svc_day ON service_days(service_id,date)")
        metadata={
            "schema":"openroad-bus-sqlite-1",
            "region":region,
            "createdOn":today.isoformat(),
            "sourceArchiveSha256":verified["archiveSha256"],
            "routeCount":nroutes,"stopCount":nstops,
            "tripCount":ntrips,"stopTimeCount":nstop_times,
            "serviceDateCount":ndays,
            "navigationGeometryVerified":False,
            "eligibleForProductionPublication":False,
            "walkingTransferConnectorsVerified":False,
            "notes":"Source-pinned timetable-only index; not a navigable route provider."
        }
        db.executemany("INSERT INTO info(name,value) VALUES(?,?)",
                       [(k,json.dumps(v)) for k,v in metadata.items()])
        db.commit()
        integrity=db.execute("PRAGMA quick_check").fetchone()[0]
        if integrity!="ok":raise FeedRejected("SQLite index integrity check failed")
        db.close();db=None
        os.replace(tmp,out)
        return metadata
    except BaseException:
        if db is not None:db.close()
        try:tmp.unlink()
        except FileNotFoundError:pass
        raise

def _sha(path):
    hasher=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):
            hasher.update(block)
    return hasher.hexdigest()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--region",required=True,choices=["south_west","west_midlands"])
    ap.add_argument("--output",required=True)
    ap.add_argument("--report",required=True)
    ap.add_argument("--today",default=dt.date.today().isoformat())
    args=ap.parse_args()
    result=build_index(args.source,args.region,args.output,
                       dt.date.fromisoformat(args.today))
    Path(args.report).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
