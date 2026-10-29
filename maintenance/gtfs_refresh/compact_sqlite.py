#!/usr/bin/env python3
"""Lossless, immutable GTFS SQLite index compaction using integer surrogate IDs.

Builds off-host from an already verified full regional index. Never touches
the input. Refuses to publish an output if any timed stop-call disappears.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sqlite3

SCHEMA = """
PRAGMA foreign_keys=OFF;
CREATE TABLE info(name TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE stops(stop_pk INTEGER PRIMARY KEY,stop_id TEXT NOT NULL UNIQUE,
                   name TEXT NOT NULL,lat REAL NOT NULL,lon REAL NOT NULL);
CREATE TABLE routes(route_id TEXT PRIMARY KEY,short_name TEXT,long_name TEXT,
                    route_type INTEGER);
CREATE TABLE trips(trip_pk INTEGER PRIMARY KEY,trip_id TEXT NOT NULL UNIQUE,
                   route_id TEXT NOT NULL,service_id TEXT NOT NULL,
                   headsign TEXT,shape_id TEXT);
CREATE TABLE calls(trip_pk INTEGER NOT NULL,seq INTEGER NOT NULL,
                   stop_pk INTEGER NOT NULL,arrival_sec INTEGER NOT NULL,
                   departure_sec INTEGER NOT NULL,pickup INTEGER NOT NULL,
                   dropoff INTEGER NOT NULL,
                   PRIMARY KEY(trip_pk,seq)) WITHOUT ROWID;
CREATE TABLE service_days(date TEXT NOT NULL,service_id TEXT NOT NULL,
                          PRIMARY KEY(date,service_id)) WITHOUT ROWID;
CREATE VIEW stop_times AS
SELECT t.trip_id,c.seq,s.stop_id,c.arrival_sec,c.departure_sec,
       c.pickup,c.dropoff
FROM calls c
JOIN trips t ON t.trip_pk=c.trip_pk
JOIN stops s ON s.stop_pk=c.stop_pk;
"""

def compact_index(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file() or destination.exists():
        raise ValueError("Missing input or destination already exists")
    dest_tmp=destination.with_name(destination.name+".incomplete")
    if dest_tmp.exists():raise ValueError("Another unfinished conversion exists")
    con=None
    try:
        con=sqlite3.connect(dest_tmp,uri=True,timeout=60)
        con.executescript(SCHEMA)
        con.execute("PRAGMA synchronous=OFF")
        con.execute("PRAGMA cache_size=-64000")
        con.execute("ATTACH DATABASE ? AS old",(source.as_uri()+"?mode=ro",))
        if con.execute("SELECT value FROM old.info WHERE name='schema'").fetchone()!=(
            json.dumps("openroad-bus-sqlite-1"),):
            raise ValueError("Input index schema unsupported")
        con.execute("INSERT INTO info SELECT name,value FROM old.info")
        con.execute("UPDATE info SET value=? WHERE name='schema'",
                    (json.dumps("openroad-bus-sqlite-compact-2"),))
        con.execute(
          "INSERT INTO stops(stop_pk,stop_id,name,lat,lon) "
          "SELECT rowid,stop_id,name,lat,lon FROM old.stops")
        con.execute("INSERT INTO routes SELECT * FROM old.routes")
        con.execute(
          "INSERT INTO trips(trip_pk,trip_id,route_id,service_id,headsign,shape_id) "
          "SELECT rowid,trip_id,route_id,service_id,headsign,shape_id FROM old.trips")
        con.execute("INSERT INTO service_days SELECT * FROM old.service_days")
        con.execute(
          "INSERT INTO calls(trip_pk,seq,stop_pk,arrival_sec,departure_sec,pickup,dropoff) "
          "SELECT t.rowid,c.seq,s.rowid,c.arrival_sec,c.departure_sec,c.pickup,c.dropoff "
          "FROM old.stop_times AS c "
          "JOIN old.trips AS t ON t.trip_id=c.trip_id "
          "JOIN old.stops AS s ON s.stop_id=c.stop_id")
        before=con.execute("SELECT count(*) FROM old.stop_times").fetchone()[0]
        after=con.execute("SELECT count(*) FROM calls").fetchone()[0]
        if before!=after:
            raise ValueError("Stop-times missing from compacted output")
        con.execute("CREATE INDEX idx_calls_depart ON calls(stop_pk,departure_sec,trip_pk)")
        con.execute("CREATE INDEX idx_calls_arrive ON calls(stop_pk,arrival_sec,trip_pk)")
        con.execute("CREATE INDEX idx_trips_service ON trips(service_id,trip_pk)")
        con.execute("CREATE INDEX idx_stops_coord ON stops(lat,lon)")
        con.execute("CREATE INDEX idx_svc_id_day ON service_days(service_id,date)")
        con.commit()
        if con.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("Compact index integrity check failed")
        # Query shape must remain exactly the same as the published oracle.
        if con.execute("SELECT count(*) FROM stop_times").fetchone()[0]!=after:
            raise ValueError("Stop-times compatibility view incomplete")
        con.close();con=None
        os.replace(dest_tmp,destination)
        return {"result":"COMPACTED_VALIDATED","rows":after,
                "originalBytes":source.stat().st_size,
                "compactBytes":destination.stat().st_size,
                "ratio":round(destination.stat().st_size/source.stat().st_size,3),
                "productionDeploymentApproved":False}
    except BaseException:
        if con is not None:con.close()
        try:dest_tmp.unlink()
        except FileNotFoundError:pass
        raise

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source");p.add_argument("output")
    a=p.parse_args()
    print(json.dumps(compact_index(a.source,a.output),sort_keys=True))
