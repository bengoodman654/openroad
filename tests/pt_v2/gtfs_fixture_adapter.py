"""Bounded offline GTFS *fixture* adapter. No network, server or Android integration.

This deliberately supports small test archives (<8 MiB uncompressed required files).
It is NOT a production national GTFS parser. It does not infer that any particular
service exists today without trip calendars and valid stop times from that archive.
"""
from __future__ import annotations

from datetime import date, datetime
from io import TextIOWrapper
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile
import csv

REQUIRED = {"routes.txt", "trips.txt", "stops.txt", "stop_times.txt"}
OPTIONAL = {"calendar.txt", "calendar_dates.txt"}
MAX_BYTES = 8 * 1024 * 1024
FIELDS = {
    "routes.txt": {"route_id", "route_short_name"},
    "trips.txt": {"route_id", "service_id", "trip_id"},
    "stops.txt": {"stop_id", "stop_name"},
    "stop_times.txt": {"trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"},
    "calendar.txt": {"service_id", "start_date", "end_date", "monday", "tuesday",
                      "wednesday", "thursday", "friday", "saturday", "sunday"},
    "calendar_dates.txt": {"service_id", "date", "exception_type"},
}

class GTFSFixtureError(ValueError):
    pass

def seconds(s):
    """GTFS hours 00..99, including 25:xx:xx after midnight."""
    parts = s.split(":")
    if len(parts) != 3 or any(not x.isdigit() for x in parts):
        raise GTFSFixtureError("Invalid GTFS time")
    h, m, sec = (int(x) for x in parts)
    if not 0 <= h <= 99 or not 0 <= m < 60 or not 0 <= sec < 60:
        raise GTFSFixtureError("Invalid GTFS time values")
    return h * 3600 + m * 60 + sec

class GTFSFixture:
    def __init__(self, rows):
        self.rows = rows
        self.routes = {x["route_id"]:x for x in rows["routes.txt"]}
        self.stops = {x["stop_id"]:x for x in rows["stops.txt"]}
        self.trips = {x["trip_id"]:x for x in rows["trips.txt"]}
        self.calendar = {x["service_id"]:x for x in rows.get("calendar.txt",[])}
        self.exceptions = {}
        for x in rows.get("calendar_dates.txt",[]):
            if x["exception_type"] not in ("1","2"):
                raise GTFSFixtureError("Invalid calendar_dates exception")
            self.exceptions[(x["service_id"],x["date"])] = x["exception_type"]
        if not self.calendar and not self.exceptions:
            raise GTFSFixtureError("No service calendar")
        self.stop_times = {}
        for s in rows["stop_times.txt"]:
            if s["trip_id"] not in self.trips or s["stop_id"] not in self.stops:
                raise GTFSFixtureError("Unresolved stop-time reference")
            try:seq=int(s["stop_sequence"])
            except ValueError:raise GTFSFixtureError("Bad stop sequence")
            arr=seconds(s["arrival_time"]);dep=seconds(s["departure_time"])
            if dep < arr:raise GTFSFixtureError("Departure precedes arrival")
            self.stop_times.setdefault(s["trip_id"],[]).append((seq,s))
        for trip in self.trips.values():
            if trip["route_id"] not in self.routes:
                raise GTFSFixtureError("Unresolved route")
            if trip["trip_id"] not in self.stop_times:
                raise GTFSFixtureError("Trip without stops")
            ordered=sorted(self.stop_times[trip["trip_id"]])
            seqs=[a for a,_ in ordered]
            if len(set(seqs))!=len(seqs):
                raise GTFSFixtureError("Duplicate stop sequence")
            last=-1
            for _,st in ordered:
                if seconds(st["arrival_time"])<last:
                    raise GTFSFixtureError("Trip timetable not monotonic")
                last=seconds(st["departure_time"])
            self.stop_times[trip["trip_id"]]=[x for _,x in ordered]

    @classmethod
    def open(cls, filename, max_bytes=MAX_BYTES):
        try:
            with ZipFile(filename) as archive:
                entries={}
                for info in archive.infolist():
                    name=info.filename.replace("\\","/")
                    p=PurePosixPath(name)
                    if info.is_dir():continue
                    if p.is_absolute() or ".." in p.parts or len(p.parts)>4:
                        raise GTFSFixtureError("Unsafe archive path")
                    if p.name not in REQUIRED|OPTIONAL:continue
                    if p.name in entries:raise GTFSFixtureError("Duplicate GTFS table")
                    entries[p.name]=info
                if not REQUIRED.issubset(entries) or not OPTIONAL.intersection(entries):
                    raise GTFSFixtureError("Missing required GTFS tables")
                if sum(i.file_size for i in entries.values())>max_bytes:
                    raise GTFSFixtureError("Fixture archive exceeds bounded limit")
                rows={}
                for table,entry in entries.items():
                    with archive.open(entry) as binary:
                        stream=TextIOWrapper(binary,encoding="utf-8-sig",newline="")
                        reader=csv.DictReader(stream)
                        if not reader.fieldnames or not FIELDS[table].issubset(reader.fieldnames):
                            raise GTFSFixtureError("Missing columns in "+table)
                        table_rows=[]
                        for row in reader:
                            if None in row:
                                raise GTFSFixtureError("Malformed CSV in "+table)
                            table_rows.append({k:str(v or "").strip() for k,v in row.items()})
                        rows[table]=table_rows
            return cls(rows)
        except (BadZipFile,UnicodeError,EOFError) as exc:
            raise GTFSFixtureError("Invalid GTFS fixture archive") from exc

    def active(self,service_id,on_date):
        ds=on_date.strftime("%Y%m%d")
        override=self.exceptions.get((service_id,ds))
        if override is not None:return override=="1"
        c=self.calendar.get(service_id)
        return bool(c and c["start_date"]<=ds<=c["end_date"]
                    and c[on_date.strftime("%A").lower()]=="1")

    def services(self,line,on_date=None):
        """Service matches by operator route ID, never by number alone."""
        matches=[]
        for route in self.routes.values():
            if route["route_short_name"].casefold()!=line.casefold():continue
            trips=[t for t in self.trips.values() if t["route_id"]==route["route_id"]
                   and (on_date is None or self.active(t["service_id"],on_date))]
            if not trips:continue
            matches.append({
                "route_id":route["route_id"],
                "line":route["route_short_name"],
                "long_name":route.get("route_long_name",""),
                "agency_id":route.get("agency_id",""),
                "trips":len(trips),
            })
        return sorted(matches,key=lambda x:(x["agency_id"],x["route_id"]))

    def trip_stop_names(self,trip_id):
        return [self.stops[st["stop_id"]]["stop_name"] for st in self.stop_times[trip_id]]
