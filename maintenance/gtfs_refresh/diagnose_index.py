"""Read-only quality report for official regional GTFS SQLite research indices.

Identifies missing boardings, overloaded stop caps and missing direct link
without publishing any route or accessing production infrastructure.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sqlite3
import time
from pathlib import Path
from maintenance.gtfs_refresh.query_sqlite import close_stops

def _nearest(db,lat,lon,radius_m,count):
    # Reuses the exact distance/bbox logic of the research planner.
    return close_stops(db,lat,lon,radius_m,count)

def diagnostic(index_path,region,origin,dest,day,depart_sec):
    if region not in ('south_west','west_midlands'):
        raise ValueError('Region not supported')
    if not isinstance(day,dt.date) or not 0<=depart_sec<=86400:
        raise ValueError('Invalid timetable day or departure')
    started=time.monotonic()
    db=sqlite3.connect('file:'+str(Path(index_path).resolve())+'?mode=ro&immutable=1',
                       uri=True,timeout=0.3)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        info={r['name']:json.loads(r['value']) for r in db.execute('SELECT * FROM info')}
        if info.get('region')!=region:
            raise ValueError('Wrong region in index')
        date=day.isoformat()
        totals={'activeServiceIds':db.execute(
            'SELECT COUNT(*) FROM service_days WHERE date=?',(date,)).fetchone()[0],
            'totalStops':db.execute('SELECT COUNT(*) FROM stops').fetchone()[0],
            'totalTrips':db.execute('SELECT COUNT(*) FROM trips').fetchone()[0]}
        variants=[]
        for radius,limit in ((900,20),(900,40),(1400,40),(1800,60)):
            origins=_nearest(db,*origin,radius,limit)
            destinations=_nearest(db,*dest,radius,limit)
            eligible={r[1] for r in destinations}
            boards=0
            direct=set()
            active_lines=set()
            if totals['activeServiceIds']>0:
                for walk,stop_id,_ in origins:
                    q=db.execute(
                        'SELECT s.trip_id,s.seq,s.departure_sec,r.short_name '
                        'FROM stop_times s JOIN trips t ON t.trip_id=s.trip_id '
                        'JOIN routes r ON r.route_id=t.route_id '
                        'JOIN service_days d ON d.service_id=t.service_id AND d.date=? '
                        'WHERE s.stop_id=? AND s.pickup=0 AND '
                        's.departure_sec BETWEEN ? AND ? '
                        'ORDER BY s.departure_sec LIMIT 48',
                        (date,stop_id,depart_sec+int(walk/1.25),
                         depart_sec+4*3600))
                    for b in q:
                        boards+=1
                        active_lines.add(b['short_name'])
                        for alight in db.execute(
                            'SELECT stop_id FROM stop_times WHERE trip_id=? '
                            'AND seq>? AND dropoff=0 ORDER BY seq LIMIT 65',
                            (b['trip_id'],b['seq'])):
                            if alight['stop_id'] in eligible:
                                direct.add(b['trip_id'])
            variants.append({'radiusMetres':radius,'stopLimit':limit,
                'originStops':len(origins),'destinationStops':len(destinations),
                'scheduledBoardings':boards,'possibleDirectTrips':len(direct),
                'activeDistinctLines':len(active_lines)})
        return {'region':region,'serviceDate':date,'sourceArchiveSha256':
                info.get('sourceArchiveSha256'),'schema':info.get('schema'),
                'totals':totals,'variants':variants,
                'elapsedMs':round(1000*(time.monotonic()-started))}
    finally:
        db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('index')
    p.add_argument('--region',required=True,choices=['south_west','west_midlands'])
    p.add_argument('--date',default=dt.date.today().isoformat())
    a=p.parse_args()
    points={'south_west':((51.438,-2.607),(51.459,-2.627)),
            'west_midlands':((52.4068,-1.5197),(52.420,-1.505))}
    result=diagnostic(a.index,a.region,*points[a.region],
                      dt.date.fromisoformat(a.date),9*3600)
    print('GTFS_COVERAGE_DIAGNOSIS='+json.dumps(result,sort_keys=True))
