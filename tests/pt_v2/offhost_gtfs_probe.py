#!/usr/bin/env python3
"""One bounded OFF-HOST probe of the DfT regional GTFS ZIP, no shared hosting touched.

Print route/operator metadata only, not complete raw timetables, and never emit
claims about valid operating dates until calendar/trip checks are implemented.
"""
import argparse
import csv
import hashlib
from io import TextIOWrapper
import json
from pathlib import Path
import tempfile
from urllib.parse import urlparse
from urllib.request import Request,urlopen
import zipfile

ALLOW={
  "west_midlands":"https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/west_midlands/",
  "south_west":"https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_west/"
}
TARGETS={
  "west_midlands":["9","11","12X"],
  "south_west":["75"]
}

def download(source,dest,cap_bytes):
    req=Request(source,headers={"User-Agent":"OpenRoad-PTv2-GTFS-offhost-audit/1.0","Accept":"application/zip, application/octet-stream, */*"})
    h=hashlib.sha256();count=0
    with urlopen(req,timeout=35) as response,open(dest,"wb") as output:
        final=urlparse(response.geturl())
        if final.scheme!="https" or final.hostname!="data.bus-data.dft.gov.uk":
            raise ValueError("Redirect to unexpected host; blocked")
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            count+=len(chunk)
            if count>cap_bytes:raise ValueError("Compressed archive exceeded safe size limit")
            output.write(chunk)
            h.update(chunk)
    return count,h.hexdigest()

def records(z,name,bytecap=64*1024*1024):
    found=[x for x in z.infolist() if Path(x.filename).name.lower()==name]
    if len(found)!=1:
        raise ValueError("Missing or duplicated "+name)
    if found[0].file_size>bytecap:raise ValueError(name+" exceeds inspection bound")
    with z.open(found[0]) as stream:
        reader=csv.DictReader(TextIOWrapper(stream,encoding="utf-8-sig",newline=""))
        for row in reader:yield row

def inspect(path,area):
    with zipfile.ZipFile(path) as zipfile_obj:
        agencies={r.get("agency_id",""):r.get("agency_name","") for r in records(zipfile_obj,"agency.txt")}
        routes=[]
        for row in records(zipfile_obj,"routes.txt"):
            line=(row.get("route_short_name") or "").strip().upper()
            if line not in TARGETS[area]:continue
            routes.append({
                "route_id":row.get("route_id",""),
                "line":line,
                "agency_id":row.get("agency_id",""),
                "agency_name":agencies.get(row.get("agency_id",""),""),
                "long_name":(row.get("route_long_name") or "")[:160]
            })
    counts={s:sum(r["line"]==s for r in routes) for s in TARGETS[area]}
    # Never print potentially thousands of aliases; show just the first 20 for each line.
    return {
      "route_candidates_by_public_number":counts,
      "samples":{line:[r for r in routes if r["line"]==line][:20] for line in TARGETS[area]},
      "scope":"Actual publisher GTFS routes/agency metadata, NOT trip/date/stop/geometry integration acceptance."
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--region",choices=ALLOW,required=True)
    parser.add_argument("--max-download-mib",type=int,default=140)
    args=parser.parse_args()
    if not 1<=args.max_download_mib<=160:
        parser.error("download bound must be 1..160 MiB")
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"official-gtfs.zip"
        size,sha=download(ALLOW[args.region],p,args.max_download_mib*1024*1024)
        facts=inspect(p,args.region)
    print(json.dumps({
      "source":ALLOW[args.region],
      "region":args.region,
      "downloaded_bytes":size,
      "archive_sha256":sha,
      "results":facts,
      "production_acceptance_cases_passed":0,
    },indent=2))
if __name__=="__main__":main()
