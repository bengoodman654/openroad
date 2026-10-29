#!/usr/bin/env python3
"""Validate an official BODS regional GTFS archive without extracting it.

This script performs no writes to the live OpenRoad server. It produces only
bounded counts, source digest and a provenance manifest on the GitHub runner.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import pathlib
import re
import zipfile

REGIONS = {
    "south_west": (51.4545, -2.5879),  # Bristol
    "west_midlands": (52.4068, -1.5197),  # Coventry
}
MANDATORY = {"agency.txt","routes.txt","trips.txt","stops.txt",
             "stop_times.txt"}
REQUIRED_COLUMNS={
    "stops.txt":{"stop_id","stop_lat","stop_lon"},
    "routes.txt":{"route_id"},
    "trips.txt":{"trip_id","route_id","service_id"},
    "stop_times.txt":{"trip_id","stop_id","stop_sequence"},
}
MAX_ZIP_BYTES=700*1024*1024
MAX_UNCOMPRESSED_BYTES=6*1024*1024*1024
MAX_CSV_ROWS={"stops.txt":600000,"routes.txt":100000,
              "trips.txt":2000000,"calendar.txt":200000,
              "calendar_dates.txt":400000}
FUTURE_DAYS=28

class FeedRejected(ValueError):
    pass

def safe_members(z:zipfile.ZipFile):
    out={}
    total=0
    for member in z.infolist():
        name=member.filename
        if member.is_dir():
            continue
        if name.startswith("/") or "\\\\" in name or ".." in pathlib.PurePosixPath(name).parts:
            raise FeedRejected("Unsafe ZIP member name")
        if member.flag_bits & 1:
            raise FeedRejected("Encrypted GTFS member")
        base=pathlib.PurePosixPath(name).name.lower()
        if base in out:
            raise FeedRejected("Ambiguous duplicate GTFS member")
        if member.file_size<0 or member.file_size>MAX_UNCOMPRESSED_BYTES:
            raise FeedRejected("Unbounded GTFS member")
        total+=member.file_size
        if total>MAX_UNCOMPRESSED_BYTES:
            raise FeedRejected("Unbounded archive expansion")
        out[base]=member
    if not MANDATORY.issubset(out):
        raise FeedRejected("Missing required GTFS tables")
    if "calendar.txt" not in out and "calendar_dates.txt" not in out:
        raise FeedRejected("GTFS has no timetable calendar")
    return out

def rows(z:zipfile.ZipFile, member, required=frozenset(), limit=2000000):
    with z.open(member) as handle:
        wrapper=io.TextIOWrapper(handle,encoding="utf-8-sig",errors="strict",newline="")
        reader=csv.DictReader(wrapper)
        fields=set(reader.fieldnames or ())
        if not required.issubset(fields):
            raise FeedRejected("Missing required GTFS columns")
        for ix,row in enumerate(reader):
            if ix>=limit:
                raise FeedRejected("GTFS table row limit reached")
            yield row

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while True:
            block=f.read(1024*1024)
            if not block:break
            h.update(block)
    return h.hexdigest()

def parse_ymd(raw):
    if not isinstance(raw,str) or not re.fullmatch(r"\d{8}",raw):
        return None
    try:
        return dt.datetime.strptime(raw,"%Y%m%d").date()
    except ValueError:
        return None

def validate_archive(path,region,today):
    path=pathlib.Path(path)
    if region not in REGIONS:
        raise FeedRejected("Unsupported region")
    if not path.is_file() or path.stat().st_size<10000 or path.stat().st_size>MAX_ZIP_BYTES:
        raise FeedRejected("Missing or oversized GTFS file")
    if not zipfile.is_zipfile(path):
        raise FeedRejected("File is not a GTFS ZIP")
    lat,lon=REGIONS[region]
    stop_count=nearby=route_count=trip_count=0
    table_columns={}
    max_service_date=None
    min_service_date=None
    service_additions=0
    with zipfile.ZipFile(path) as z:
        members=safe_members(z)
        if z.testzip() is not None:
            raise FeedRejected("GTFS archive fails CRC check")
        for name,req in REQUIRED_COLUMNS.items():
            with z.open(members[name]) as fh:
                reader=csv.reader(io.TextIOWrapper(fh,encoding="utf-8-sig",newline=""))
                h=set(next(reader,[]))
                if not req.issubset(h):
                    raise FeedRejected("Bad GTFS columns in "+name)
                table_columns[name]=sorted(h & req)
        for stop in rows(z,members["stops.txt"],REQUIRED_COLUMNS["stops.txt"],
                         MAX_CSV_ROWS["stops.txt"]):
            stop_count+=1
            try:
                a=float(stop["stop_lat"]); b=float(stop["stop_lon"])
                if not math.isfinite(a) or not math.isfinite(b) or abs(a)>90 or abs(b)>180:
                    raise FeedRejected("Invalid GTFS stop coordinate")
            except (TypeError,ValueError) as e:
                raise FeedRejected("Invalid GTFS stop coordinate") from e
            if abs(a-lat)<0.18 and abs(b-lon)<0.22:
                nearby+=1
        for route in rows(z,members["routes.txt"],REQUIRED_COLUMNS["routes.txt"],
                          MAX_CSV_ROWS["routes.txt"]):
            if not route["route_id"].strip():
                raise FeedRejected("Missing route identifier")
            route_count+=1
        for trip in rows(z,members["trips.txt"],REQUIRED_COLUMNS["trips.txt"],
                         MAX_CSV_ROWS["trips.txt"]):
            if not trip["trip_id"] or not trip["route_id"] or not trip["service_id"]:
                raise FeedRejected("Missing GTFS trip identity")
            trip_count+=1
        if "calendar.txt" in members:
            for row in rows(z,members["calendar.txt"],
                            {"service_id","start_date","end_date"},
                            MAX_CSV_ROWS["calendar.txt"]):
                first=parse_ymd(row["start_date"])
                last=parse_ymd(row["end_date"])
                if first and last and first<=last:
                    min_service_date=min(first,min_service_date) if min_service_date else first
                    max_service_date=max(last,max_service_date) if max_service_date else last
        if "calendar_dates.txt" in members:
            for row in rows(z,members["calendar_dates.txt"],
                            {"service_id","date","exception_type"},
                            MAX_CSV_ROWS["calendar_dates.txt"]):
                if row["exception_type"]!="1": continue
                day=parse_ymd(row["date"])
                if not day:continue
                service_additions+=1
                min_service_date=min(day,min_service_date) if min_service_date else day
                max_service_date=max(day,max_service_date) if max_service_date else day
    if nearby<10 or stop_count<100 or route_count<10 or trip_count<50:
        raise FeedRejected("Not enough regional bus coverage")
    if not max_service_date or max_service_date < today+dt.timedelta(days=FUTURE_DAYS):
        raise FeedRejected("Future timetable calendar coverage insufficient")
    if min_service_date and min_service_date>today+dt.timedelta(days=5):
        raise FeedRejected("No service calendar around today")
    return {
       "result":"VALIDATED_SOURCE_ONLY","region":region,
       "archiveSha256":sha256_file(path),
       "compressedBytes":path.stat().st_size,
       "stops":stop_count,"stopsNearReferenceCity":nearby,
       "routes":route_count,"trips":trip_count,
       "calendarEarliest":min_service_date.isoformat() if min_service_date else None,
       "calendarLatest":max_service_date.isoformat(),
       "daysUntilLatestCalendar":(max_service_date-today).days,
       "calendarExceptionAdditions":service_additions,
       "validatedOn":today.isoformat(),
       "sourceMayContainStaleIndividualTrips":True,
       "productionDeploymentApproved":False,
       "notes":"Archive structural, geographic and calendar checks only. No live server replacement."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("zip_path")
    p.add_argument("--region",required=True,choices=REGIONS)
    p.add_argument("--output")
    p.add_argument("--today",default=dt.date.today().isoformat())
    a=p.parse_args()
    try:
        result=validate_archive(a.zip_path,a.region,dt.date.fromisoformat(a.today))
    except (FeedRejected,zipfile.BadZipFile,UnicodeError,EOFError) as error:
        print(json.dumps({"result":"REJECTED","reason":str(error)}))
        raise SystemExit(1)
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.output:
        pathlib.Path(a.output).write_text(text,encoding="utf-8")
    print(text)

if __name__=="__main__":
    main()
