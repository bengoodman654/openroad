#!/usr/bin/env python3
"""OpenRoad: compile compact, indexed and read-only rail SQLite timetable off-host."""
import argparse,csv,datetime as dt,io,json,collections,hashlib,sqlite3,zlib
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo
TZ=ZoneInfo("Europe/London")
def rows(z,n):
    matches=[x for x in z.namelist() if x.split("/")[-1].lower()==n]
    if not matches: return ()
    return csv.DictReader(io.TextIOWrapper(z.open(matches[0]),encoding="utf-8-sig"))
def clock(s):
    h,m,x=map(int,s.split(":"))
    if h>48 or m>59 or x>59 or min(h,m,x)<0: raise ValueError("bad GTFS time")
    return h*3600+m*60+x
def build(source,dest,today=None):
    today=today or dt.datetime.now(TZ).date()
    days=[today+dt.timedelta(days=n) for n in (-1,0,1,2,3)]
    dest=Path(dest)
    with ZipFile(source) as z:
        names={};stations={}
        for r in rows(z,"stops.txt"):
            code=(r.get("stop_code") or "").upper().strip()
            if len(code)!=3 or not code.isalpha():continue
            try: lat,lon=float(r["stop_lat"]),float(r["stop_lon"])
            except (ValueError,KeyError):continue
            if not (49<=lat<=61 and -9<=lon<=3):continue
            names[r["stop_id"]]=code
            if code not in stations or r.get("location_type")=="1":
                stations[code]=[(r.get("stop_name") or code)[:100],round(lat,6),round(lon,6)]
        for r in rows(z,"stops.txt"):
            if r["stop_id"] not in names and r.get("parent_station") in names:
                names[r["stop_id"]]=names[r["parent_station"]]
        if len(stations)<1000:raise ValueError("Rail source missing stations")
        active=collections.defaultdict(set)
        days_by_name=("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
        for r in rows(z,"calendar.txt"):
            for d in days:
                if r["start_date"]<=d.strftime("%Y%m%d")<=r["end_date"] and r.get(days_by_name[d.weekday()])=="1":
                    active[r["service_id"]].add(d)
        for r in rows(z,"calendar_dates.txt"):
            try:d=dt.datetime.strptime(r["date"],"%Y%m%d").date()
            except (KeyError,ValueError):continue
            if d not in days:continue
            if r["exception_type"]=="1":active[r["service_id"]].add(d)
            if r["exception_type"]=="2":active[r["service_id"]].discard(d)
        routes={r["route_id"]:(r.get("route_short_name") or "Train")[:24] for r in rows(z,"routes.txt")}
        trips={}
        for r in rows(z,"trips.txt"):
            if active.get(r["service_id"]):
                trips[r["trip_id"]]=(active[r["service_id"]],routes.get(r["route_id"],"Train"),
                    (r.get("trip_headsign") or "")[:64],(r.get("shape_id") or "")[:96])
        calls=collections.defaultdict(list)
        for r in rows(z,"stop_times.txt"):
            trip=r.get("trip_id");code=names.get(r.get("stop_id"))
            if trip not in trips or code not in stations:continue
            try:calls[trip].append((int(r["stop_sequence"]),code,clock(r["arrival_time"]),clock(r["departure_time"])))
            except (KeyError,ValueError):continue
        dest.mkdir(parents=True,exist_ok=True)
        database=dest/"events.sqlite"
        conn=sqlite3.connect(database)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-16000")
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("CREATE TABLE events (o TEXT NOT NULL, dep INTEGER NOT NULL, trip INTEGER NOT NULL, d TEXT NOT NULL, arr INTEGER NOT NULL, line TEXT NOT NULL, PRIMARY KEY (o,dep,trip,d,arr)) WITHOUT ROWID")
        conn.execute("CREATE TABLE train_info (trip INTEGER PRIMARY KEY, gtfs_id TEXT NOT NULL, headsign TEXT NOT NULL, shape_id TEXT, calls BLOB NOT NULL)")
        conn.execute("CREATE TABLE rail_shapes (shape_id TEXT PRIMARY KEY, points BLOB NOT NULL)")
        ids={trip:i+1 for i,trip in enumerate(calls)}
        total=0
        batch=[]; trip_info=[]
        for trip,seq in calls.items():
            if len(seq)<2:continue
            seq.sort()
            meta=trips[trip]
            compact=[[p[1],p[2],p[3]] for p in seq]
            trip_info.append((ids[trip],trip[:120],meta[2],meta[3],
                zlib.compress(json.dumps(compact,separators=(",",":")).encode(),6)))
        conn.executemany("INSERT INTO train_info VALUES (?,?,?,?,?)",trip_info)
        del trip_info
        # The feed's shapes contain passing stations, not an exact railway-track
        # survey. We still retain them for truthful, higher-resolution geometry.
        by_shape=collections.defaultdict(list)
        for r in rows(z,"shapes.txt"):
            sid=r.get("shape_id")
            if not sid or len(sid)>96:continue
            try:
                sequence=int(r["shape_pt_sequence"])
                lat=round(float(r["shape_pt_lat"]),5)
                lon=round(float(r["shape_pt_lon"]),5)
            except (KeyError,ValueError):continue
            if 49<=lat<=61 and -9<=lon<=3 and len(by_shape[sid])<2400:
                by_shape[sid].append((sequence,lat,lon))
        for sid,pts in by_shape.items():
            pts.sort()
            coords=[[p[1],p[2]] for p in pts]
            conn.execute("INSERT INTO rail_shapes VALUES (?,?)",
                (sid,zlib.compress(json.dumps(coords,separators=(",",":")).encode(),6)))
        shapes_count=len(by_shape)
        del by_shape
        conn.execute("BEGIN")
        for trip,call in calls.items():
            call.sort()
            ds,line,head,shape_id=trips[trip]
            for day in ds:
                def epoch(sec):
                    d2=day+dt.timedelta(days=sec//86400)
                    return int(dt.datetime.combine(d2,dt.time(sec//3600%24,sec//60%60,sec%60),TZ).timestamp())
                for a,b in zip(call,call[1:]):
                    if a[1]==b[1]:continue
                    dep,arr=epoch(a[3]),epoch(b[2])
                    if dep>=arr or arr-dep>8*3600:continue
                    batch.append((a[1],dep,ids[trip],b[1],arr,line))
                    total+=1
                    if len(batch)>=5000:
                        conn.executemany("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",batch)
                        batch.clear()
        if batch:conn.executemany("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",batch)
        conn.commit()
        conn.execute("PRAGMA optimize")
        conn.close()
        if total<30000:raise ValueError("Rail timetable missing active connections")
        (dest/"stations.json").write_text(json.dumps(stations,separators=(",",":"),ensure_ascii=False))
        manifest={"version":3,"from":days[0].isoformat(),"through":days[-1].isoformat(),
                  "stations":len(stations),"connections":total,"railShapes":shapes_count,
                  "source":"GB Transit / Rail Delivery Group timetable",
                  "built_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                  "source_sha256":hashlib.sha256(Path(source).read_bytes()).hexdigest()}
        (dest/"manifest.json").write_text(json.dumps(manifest,separators=(",",":")))
        return manifest
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("zip");p.add_argument("output")
    a=p.parse_args();print(json.dumps(build(a.zip,a.output),indent=2))
