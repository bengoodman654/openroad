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
                    cancel=lambda:False,walk_cap_m=900,
                    verified_transfers=None,avoid_steps=False):
    started=time.monotonic()
    def check():
        if cancel():raise SearchCancelled()
        if time.monotonic()-started>budget_secs:raise SearchBudget()
    if not 0<=earliest_secs<=172800 or not 0<walk_cap_m<=2000:
        raise ValueError("Unsupported research query constraints")
    uri="file:"+str(index_path)+"?mode=ro&immutable=1"
    db=sqlite3.connect(uri,uri=True,timeout=0.5)
    db.row_factory=sqlite3.Row
    # SQLite can spend most of its time inside a single multi-table query;
    # Python-level cancellation between queries is not sufficient.
    interrupted=None
    def sqlite_progress():
        nonlocal interrupted
        if cancel():
            interrupted="cancel"
            return 1
        if time.monotonic()-started>budget_secs:
            interrupted="budget"
            return 1
        return 0
    db.set_progress_handler(sqlite_progress,1000)
    try:
        db.execute("PRAGMA query_only=ON")
        info={r["name"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM info")}
        if info.get("region")!=region or info.get("schema") not in ("openroad-bus-sqlite-1","openroad-bus-sqlite-compact-2"):
            raise ValueError("Source pinned timetable mismatch")
        from maintenance.gtfs_refresh.verified_transfer import reviewed_transfer_links
        reviewed_by_board=reviewed_transfer_links(
            db,info,verified_transfers,walk_cap_m,avoid_steps=avoid_steps)
        # Retain more stop candidates for broad walking preferences.
        # A hard 20-stop cap missed busy interchanges; a larger radius
        # must not silently discard previously eligible nearby stops.
        stop_limit=min(48,max(24,int(math.ceil(walk_cap_m/40))))
        origin=close_stops(db,*from_point,walk_cap_m,stop_limit)
        destination=close_stops(db,*to_point,walk_cap_m,stop_limit)
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
              "ORDER BY s.departure_sec,t.trip_id,s.seq LIMIT 30",
              (day,stop_id,earliest,earliest_secs+3*3600)).fetchall()
            for board in boards:
                check()
                for end in db.execute(
                        "SELECT stop_id,arrival_sec,seq FROM stop_times "
                        "WHERE trip_id=? AND seq>? AND dropoff=0 "
                        "ORDER BY seq LIMIT 60",
                        (board["trip_id"],board["seq"])):
                    if end["stop_id"] in eligible:
                        if walk+eligible[end["stop_id"]]>walk_cap_m:
                            continue
                        foot=int(math.ceil(eligible[end["stop_id"]]/1.25))
                        record={
                          "trips":[board["trip_id"]],
                          "boarding":[stop_id],
                          "alighting":[end["stop_id"]],
                          "departureSec":board["departure_sec"],
                          "arrivalLowerBoundSec":end["arrival_sec"]+foot,
                          "operatorLine":board["short_name"],
                          "accessWalkMetresLowerBound":round(walk),
                          "egressWalkMetresLowerBound":round(eligible[end["stop_id"]]),
                          "transferWalkMetres":0,
                          "transferGeometryVerified":False,
                        }
                        key=(board["trip_id"],stop_id,end["stop_id"],board["departure_sec"])
                        if key not in seen:
                            seen.add(key);records.append(record)
                    else:
                        # Transfer candidates: only later stops on same trip.
                        first_legs.append((end["arrival_sec"],end["stop_id"],
                            board["trip_id"],stop_id,board["departure_sec"],
                            board["short_name"],walk))
        # Search backwards from actual destination arrivals. A global
        # early-arrival slice of first-leg stops is not representative:
        # crowded routes can otherwise exclude useful change stops.
        # Every transfer below remains at the EXACT SAME stop ID; never
        # infer that two nearby stops have a safe pedestrian connection.
        from collections import defaultdict
        first_by_stop=defaultdict(list)
        for leg in first_legs:
            if leg[0] >= earliest_secs and leg[0] <= earliest_secs+5*3600:
                first_by_stop[leg[1]].append(leg)
        for legs in first_by_stop.values():
            legs.sort(key=lambda x:(x[0],x[2],x[3]))
        # Only destination-serving second trips need to be inspected.
        # Indexed destination-stop queries bound memory and database work.
        transfer_count=0
        for dest_walk,dest_stop,_ in destination:
            check()
            alights=db.execute(
              "SELECT s.trip_id,s.seq,s.arrival_sec,r.short_name "
              "FROM stop_times s JOIN trips t ON t.trip_id=s.trip_id "
              "JOIN routes r ON r.route_id=t.route_id "
              "JOIN service_days d ON d.service_id=t.service_id AND d.date=? "
              "WHERE s.stop_id=? AND s.dropoff=0 "
              "AND s.arrival_sec BETWEEN ? AND ? "
              "ORDER BY s.arrival_sec,s.trip_id,s.seq LIMIT 50",
              (day,dest_stop,earliest_secs+180,
               earliest_secs+6*3600)).fetchall()
            for alight in alights:
                check()
                # A second trip can board only at a preceding stop with
                # explicit pickup permission, and no later than alighting.
                previous=db.execute(
                   "SELECT stop_id,departure_sec FROM stop_times "
                   "WHERE trip_id=? AND seq<? AND pickup=0 "
                   "ORDER BY seq DESC LIMIT 70",
                   (alight["trip_id"],alight["seq"]))
                for board2 in previous:
                    board_stop=board2["stop_id"]
                    choices=[(board_stop,None)]
                    choices.extend((path.a,path)
                                   for path in reviewed_by_board.get(board_stop,()))
                    second_depart=board2["departure_sec"]
                    if second_depart<earliest_secs+180:continue
                    for alight_stop,footpath in choices:
                        if alight_stop not in first_by_stop:continue
                        walking_seconds=footpath.seconds if footpath else 0
                        walking_metres=footpath.metres if footpath else 0
                        for arr,_,first_trip,boarding,departure,line,access_walk in first_by_stop[alight_stop]:
                            if arr+walking_seconds+180>second_depart:break
                            if second_depart>arr+walking_seconds+3600 or first_trip==alight["trip_id"]:
                                continue
                            # Only the reviewed middle connector has path
                            # geometry. The endpoint access/egress values
                            # remain great-circle LOWER BOUNDS, so every
                            # itinerary stays research-only/nonselectable.
                            if access_walk+walking_metres+dest_walk>walk_cap_m:
                                continue
                            key=(first_trip,alight["trip_id"],boarding,
                                 alight_stop,board_stop,dest_stop)
                            if key in seen:continue
                            seen.add(key)
                            records.append({
                              "trips":[first_trip,alight["trip_id"]],
                              "boarding":[boarding,board_stop],
                              "alighting":[alight_stop,dest_stop],
                              "departureSec":departure,
                              "arrivalLowerBoundSec":alight["arrival_sec"]+
                                  int(math.ceil(dest_walk/1.25)),
                              "operatorLine":line+" → "+alight["short_name"],
                              "accessWalkMetresLowerBound":round(access_walk),
                              "egressWalkMetresLowerBound":round(dest_walk),
                              "transferWalkMetres":walking_metres,
                              "transferWalkSeconds":walking_seconds,
                              "transferWalkGeometry":list(footpath.geometry) if footpath else [],
                              "transferGeometryVerified":bool(footpath),
                            })
                            transfer_count+=1
                            if transfer_count>=5000:break
                        if transfer_count>=5000:break
                    if transfer_count>=5000:break
                if transfer_count>=5000:break
            if transfer_count>=5000:break
        records.sort(key=lambda r:(r["arrivalLowerBoundSec"],r["departureSec"],
                                  len(r["trips"]),tuple(r["trips"]),
                                  tuple(r["boarding"]),tuple(r["alighting"])))
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
    except sqlite3.OperationalError as exc:
        if interrupted=="cancel":
            raise SearchCancelled() from exc
        if interrupted=="budget":
            raise SearchBudget() from exc
        raise
    finally:
        db.set_progress_handler(None,0)
        db.close()


def timetable_query(index_path,region,from_point,to_point,
                    service_date,earliest_secs,budget_secs=4,
                    cancel=lambda:False,walk_cap_m=900,
                    verified_transfers=None,avoid_steps=False):
    """Merge current and previous service days for GTFS 24+ hour journeys."""
    if not isinstance(service_date,dt.date):
        raise ValueError("Service date required")
    started=time.monotonic()
    current=_query_one_service_day(index_path,region,from_point,to_point,
                                   service_date,earliest_secs,
                                   budget_secs,cancel,walk_cap_m,
                                   verified_transfers,avoid_steps)
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
        remain,cancel,walk_cap_m,verified_transfers,avoid_steps)
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
