#!/usr/bin/env python3
"""Inspect a GTFS ZIP from an approved publisher offline; never download or publish it.

Produces source- and date-labelled candidate records for human verification.
Matching a route number is NOT confirmation of the operator, exact trip or timetable.
"""
from __future__ import annotations
import argparse
from datetime import date
from pathlib import Path
import hashlib
import json
import re
import sys
from gtfs_fixture_adapter import GTFSFixture, GTFSFixtureError

def normal(s):
    return re.sub(r"[^a-z0-9]+"," ",s.casefold()).strip()

def matches_label(needle,label):
    n=normal(needle)
    hay=normal(label)
    return bool(n and n in hay)

def inspect(gtfs, reference, service_date):
    report=[]
    for case in reference["cases"]:
        candidates=[]
        for route in gtfs.services(case["line"],service_date):
            trips=[]
            for trip in gtfs.trips.values():
                if trip["route_id"]!=route["route_id"] or not gtfs.active(trip["service_id"],service_date):
                    continue
                stop_names=gtfs.trip_stop_names(trip["trip_id"])
                endpoints_found=[
                    any(matches_label(expected,stop) for stop in stop_names)
                    for expected in case["endpoints"]
                ]
                via_found=[
                    any(matches_label(expected,stop) for stop in stop_names)
                    for expected in case["via"]
                ]
                if all(endpoints_found):
                    trips.append({
                        "trip_id":trip["trip_id"],
                        "termini_found":True,
                        "via_found":all(via_found),
                        "stop_count":len(stop_names)
                    })
            candidates.append({
                "route_id":route["route_id"],
                "agency_id":route["agency_id"],
                "short_name":route["line"],
                "candidate_trip_patterns":trips[:5],
                "possible_endpoint_match":bool(trips)
            })
        report.append({
            "case":case["id"],
            "public_line":case["line"],
            "requested_area":case["area"],
            "published_operator":case["provider"],
            "source_scope":"public route metadata only",
            "candidate_count":len(candidates),
            "candidates":candidates[:15],
            "evaluation":("CANDIDATE_REVIEW_REQUIRED" if candidates else "NO_MATCH_IN_SUPPLIED_ARCHIVE"),
            "note":"Never mark production acceptance PASS without operator/pattern IDs, authoritative date-specific schedule and independent oracle."
        })
    return report

def stream_sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive",type=Path,required=True,help="Local, previously downloaded GTFS ZIP; no network access")
    ap.add_argument("--reference",type=Path,default=Path(__file__).resolve().parents[2]/"docs/public-transport-v2/fixtures/bristol_coventry_reference.json")
    ap.add_argument("--date",required=True,help="Requested service date YYYY-MM-DD (not current wall-clock time)")
    ap.add_argument("--source-url",required=True,help="Publisher/feed provenance, not downloaded by this tool")
    ap.add_argument("--max-mib",type=int,default=8,help="Bound on uncompressed core tables. Fixture default 8 MiB.")
    ap.add_argument("--output",type=Path,default=None)
    args=ap.parse_args()
    if not (1<=args.max_mib<=256):
        ap.error("--max-mib must be between 1 and 256")
    if args.archive.suffix.lower()!=".zip" or not args.archive.is_file():
        ap.error("Provide an existing local .zip archive")
    if not args.source_url.startswith("https://"):
        ap.error("Source URL must be HTTPS")
    try:
        d=date.fromisoformat(args.date)
        reference=json.loads(args.reference.read_text(encoding="utf-8"))
        gtfs=GTFSFixture.open(args.archive,max_bytes=args.max_mib*1024*1024)
        report={
            "kind":"GTFS_IMPORT_INSPECTION_NOT_PRODUCTION_ACCEPTANCE",
            "service_date":d.isoformat(),
            "archive_sha256":stream_sha256(args.archive),
            "source_url":args.source_url,
            "archive_name":args.archive.name,
            "schema":"openroad.pt.gtfs-inspection.v1",
            "cases":inspect(gtfs,reference,d),
            "real_integration_cases_passed":0,
        }
        out=json.dumps(report,indent=2)+"\n"
        if args.output:args.output.write_text(out,encoding="utf-8")
        else:sys.stdout.write(out)
    except (GTFSFixtureError,ValueError,OSError,KeyError) as e:
        print("GTFS inspection blocked: "+str(e),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":raise SystemExit(main())
