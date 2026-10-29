#!/usr/bin/env python3
"""Read-only, bounded schedule-only bus research against off-host SQLite index.

Outputs no pedestrian routes and cannot mark any option selectable. It is an
engineering oracle for source coverage and API design, not turn-by-turn nav.
"""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import math
import sqlite3
import time

class SearchCancelled(Exception):pass
class SearchBudget(Exception):pass

def metres(a,b):
    lat1,lon1=a;lat2,lon2=b
    p1=math.radians(lat1);p2=math.radians(lat2)
    dp=p2-p1;dl=math.radians(lon2-lon1)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371000*2*math.atan2(math.sqrt(x),math.sqrt(max(0,1-x)))

def close_stops(db,lat,lon,radius_m=1000,limit=15):
    deg=radius_m/111200
    londeg=deg/max(0.3,abs(math.cos(math.radians(lat))))
    raw=db.execute(
      "SELECT stop_id,lat,lon,name FROM stops "
      "WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
      (lat-deg,lat+deg,lon-londeg,lon+londeg))
    out=[]
    for s in raw:
        d=metres((lat,lon),(s["lat"],s["lon"]))
        if d<=radius_m:out.append((d,s["stop_id"],s["name"]))
    return sorted(out)[:limit]

def _query_one_service_day(index_path,region,from_point,to_point,
                    service_date,earliest_secs,budget_secs=4,
                    cancel=lambda:False,walk_cap_m=900):
    started=time.monotonic()
    def check():
        if cancel():raise SearchCancelled()
        if time.monotonic()-started>budget_secs:raise SearchBudget()
    if not 0<=earliest_secs<=172800 or not 0<walk_cap_m<=2000:
        raise ValueError("Unsupported research query constraints")
    uri="file:"+str(index_path)+"?mode=ro&immutable=1"
    db=sqlite3.connect(uri,uri=True,timeout=0.5)
    db.row_factory=sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        info={r["name"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM info")}
        if info.get("region")!=region or info.get("schema") not in ("openroad-bus-sqlite-1","openroad-bus-sqlite-compact-2"):
            raise ValueError("Source pinned timetable mismatch")
        origin=close_stops(db,*from_point,walk_cap_m,20)
        destination=close_stops(db,*to_point,walk_cap_m,20)
        if not origin or not destination:
            return {"outcome":"COVERAGE_MISSING","results":[],"researchOnly":True}
        eligible={x[1]:x[0] for x in destination}
        day=service_date.isoformat()
        if not db.execute("SELECT 1 FROM service_days WHERE date=? LIMIT 1",(day,)).fetchone():
            return {"outcome":"CALENDAR_MISSING","results":[],"researchOnly":True}
        records=[]
        first_legs=[]
        seen=set()
        for walk,stop_id,_ in origin:
            check()
            earliest=earliest_secs+int(math.ceil(walk/1.25))
            boards=db.execute(
              "SELECT s.trip_id,s.seq,s.departure_sec,t.service_id,t.route_id,"
              " t.headsign,r.short_name FROM stop_times s "
              "JOIN trips t ON t.trip_id=s.trip_id "
              "JOIN routes r ON r.route_id=t.route_id "
              "JOIN service_days d ON d.service_id=t.service_id AND d.date=? "
              "WHERE s.stop_id=? AND s.pickup=0 "
              "AND s.departure_sec BETWEEN ? AND ? "
              "ORDER BY s.departure_sec LIMIT 30",
              (day,stop_id,earliest,earliest_secs+3*3600)).fetchall()
            for board in boards:
                check()
                for end in db.execute(
                        "SELECT stop_id,arrival_sec,seq FROM stop_times "
                        "WHERE trip_id=? AND seq>? AND dropoff=0 "
                        "ORDER BY seq LIMIT 60",
                        (board["trip_id"],board["seq"])):
                    if end["stop_id"] in eligible:
                        foot=int(math.ceil(eligible[end["stop_id"]]/1.25))
                        record={
                          "trips":[board["trip_id"]],
                          "boarding":[stop_id],
                          "alighting":[end["stop_id"]],
                          "departureSec":board["departure_sec"],
                          "arrivalLowerBoundSec":end["arrival_sec"]+foot,
                          "operatorLine":board["short_name"],
                        }
                        key=(board["trip_id"],stop_id,end["stop_id"],board["departure_sec"])
                        if key not in seen:
                            seen.add(key);records.append(record)
                    else:
                        # Transfer candidates: only later stops on same trip.
                        first_legs.append((end["arrival_sec"],end["stop_id"],
                            board["trip_id"],stop_id,board["departure_sec"],
                            board["short_name"]))
        # Never equate proximity with a safe walk. Transfer must use the
        # exact same stop until a separate provenance-checked walk graph exists.
        for arr,change_stop,first_trip,boarding,departure,line in sorted(first_legs)[:600]:
            check()
            if len(records)>=40:break
            buses=db.execute(
              "SELECT s.trip_id,s.seq,s.departure_sec,r.short_name "
              "FROM stop_times s JOIN trips t ON t.trip_id=s.trip_id "
              "JOIN routes r ON r.route_id=t.route_id "
              "JOIN service_days d ON d.service_id=t.service_id AND d.date=? "
              "WHERE s.stop_id=? AND s.pickup=0 "
              "AND s.departure_sec BETWEEN ? AND ? ORDER BY s.departure_sec LIMIT 8",
              (day,change_stop,arr+180,arr+3600)).fetchall()
            for board2 in buses:
                check()
                if board2["trip_id"]==first_trip:continue
                for end in db.execute(
                       "SELECT stop_id,arrival_sec FROM stop_times "
                       "WHERE trip_id=? AND seq>? AND dropoff=0 "
                       "ORDER BY seq LIMIT 60",
                       (board2["trip_id"],board2["seq"])):
                    if end["stop_id"] not in eligible:continue
                    foot=int(math.ceil(eligible[end["stop_id"]]/1.25))
                    key=(first_trip,board2["trip_id"],boarding,
                         change_stop,end["stop_id"])
                    if key in seen:continue
                    seen.add(key)
                    records.append({
                      "trips":[first_trip,board2["trip_id"]],
                      "boarding":[boarding,change_stop],
                      "alighting":[change_stop,end["stop_id"]],
                      "departureSec":departure,
                      "arrivalLowerBoundSec":end["arrival_sec"]+foot,
                      "operatorLine":line+" → "+board2["short_name"],
                    })
        records.sort(key=lambda r:(r["arrivalLowerBoundSec"],r["departureSec"],
                                  len(r["trips"])))
        out=[]
        for rec in records:
            if len(out)>=3:break
            route_id=hashlib.sha256(
                json.dumps([region,info["sourceArchiveSha256"],day,rec],
                           sort_keys=True).encode()).hexdigest()[:20]
            rec.update({
               "clearRouteId":route_id,"researchOnly":True,
               "selectable":False,
               "walkGeometryVerified":False,
               "accessibilityVerified":False,
               "reasonCode":"STOP_SIDE_WALK_ACCESS_UNVERIFIED",
            })
            out.append(rec)
        return {"outcome":"OK" if out else "NO_JOURNEY",
                "snapshotId":info["sourceArchiveSha256"],
                "results":out,"researchOnly":True}
    finally:
        db.close()


def timetable_query(index_path,region,from_point,to_point,
                    service_date,earliest_secs,budget_secs=4,
                    cancel=lambda:False,walk_cap_m=900):
    """Merge current and previous service days for GTFS 24+ hour journeys."""
    if not isinstance(service_date,dt.date):
        raise ValueError("Service date required")
    started=time.monotonic()
    current=_query_one_service_day(index_path,region,from_point,to_point,
                                   service_date,earliest_secs,
                                   budget_secs,cancel,walk_cap_m)
    if earliest_secs>=4*3600:
        return current
    if cancel():raise SearchCancelled()
    remain=budget_secs-(time.monotonic()-started)
    if remain<=0.12:
        # Never claim NO_JOURNEY when budget prevented previous-day check.
        return current if current["outcome"]=="OK" else {
            "outcome":"TIME_BUDGET","results":[],"researchOnly":True}
    previous=_query_one_service_day(
        index_path,region,from_point,to_point,
        service_date-dt.timedelta(days=1),earliest_secs+86400,
        remain,cancel,walk_cap_m)
    combined=[]
    for r in current.get("results",[]):
        combined.append(r)
    for item in previous.get("results",[]):
        r=dict(item)
        r["departureSec"]-=86400
        r["arrivalLowerBoundSec"]-=86400
        combined.append(r)
    if combined:
        combined.sort(key=lambda x:(
            x["arrivalLowerBoundSec"],x["departureSec"],len(x["trips"])))
        return {"outcome":"OK",
                "researchOnly":True,
                "snapshotId":current.get("snapshotId") or previous.get("snapshotId"),
                "results":combined[:3]}
    if current["outcome"]=="CALENDAR_MISSING" and previous["outcome"]=="CALENDAR_MISSING":
        outcome="CALENDAR_MISSING"
    elif current["outcome"]=="COVERAGE_MISSING" or previous["outcome"]=="COVERAGE_MISSING":
        outcome="COVERAGE_MISSING"
    else:outcome="NO_JOURNEY"
    return {"outcome":outcome,"results":[],"researchOnly":True}
