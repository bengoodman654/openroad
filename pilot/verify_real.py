"""Re-run four version-pinned within-feed GTFS journeys.

Requires the EXACT BODS downloads recorded on 25 October 2026.
This never calls the live transport server or Android app.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import time
from datetime import date
from pilot.gtfs_engine import load_region, plan_stops, populate_sqlite

SERVICE_DATE = date(2026, 10, 26)
FIXTURES = {
    "Coventry": {
        "region": "west_midlands",
        "sha256": "56e2f73ee49f77023c49f35f59d9e51a264f5e3d2dfb275a3a80151806a8d27e",
        "feedVersion": "20261022_035151",
        "connections": 248929,
        "cases": [
            {
                "name": "direct_bus_17",
                "origin": "43000031201", "destination": "43000003203",
                "departAfter": 35700, "expectedArrival": 36840,
                "expectedLines": ["17"],
                "expectedTrips": ["VJ3799cf079126768238edc4d70c448eb3494bf5d6"],
            },
            {
                "name": "transfer_bus_3_to_17",
                "origin": "43000008601", "destination": "43000002101",
                "departAfter": 40920, "expectedArrival": 42420,
                "expectedLines": ["3", "17"],
                "expectedTrips": [
                    "VJ0029c45cb74f11be6a655c51e74ba6b9d2eaa59f",
                    "VJ3a97aa7c6d2f1b2f41d72d9bc5766f5fe9090ac2",
                ],
                "expectedTransferStop": "43000001002",
            },
        ],
    },
    "Bristol": {
        "region": "south_west",
        "sha256": "61417fea64467afe1396ecc7557f1cfa85e992ea46f6254587b6b6ca8d1b2e20",
        "feedVersion": "20261022_033727",
        "connections": 402788,
        "cases": [
            {
                "name": "direct_bus_1",
                "origin": "0100BRP91045", "destination": "0100BRP91028",
                "departAfter": 35700, "expectedArrival": 36660,
                "expectedLines": ["1"],
                "expectedTrips": ["VJ17e8aaf07e9cbbac2a7798fb6708571275e2d245"],
            },
            {
                "name": "transfer_bus_24_to_43",
                "origin": "0100BRX32922", "destination": "0100BRA10454",
                "departAfter": 43260, "expectedArrival": 45180,
                "expectedLines": ["24", "43"],
                "expectedTrips": [
                    "VJ0073aeeafdc235ae9404045ceb9b80d2676bb105",
                    "VJ867a8378a832a5be147505789bcb05410e61d9c0",
                ],
                "expectedTransferStop": "0100BRA46646",
            },
        ],
    },
}


def check_city(city: str, path: str) -> dict:
    expected = FIXTURES[city]
    t0 = time.monotonic()
    s = load_region(path, city, expected["region"], SERVICE_DATE)
    if s.source_sha256 != expected["sha256"]:
        raise AssertionError(f"{city}: feed SHA-256 changed, pin a new fixture")
    if s.feed_version != expected["feedVersion"]:
        raise AssertionError(f"{city}: feed version changed")
    if len(s.connections) != expected["connections"]:
        raise AssertionError(f"{city}: connection count mismatch")
    tested = []
    for case in expected["cases"]:
        result = plan_stops(s, case["origin"], case["destination"],
                            case["departAfter"])
        if result.get("outcome") != "OK":
            raise AssertionError(f"{city}/{case['name']}: no complete itinerary")
        if result["arrival"] != case["expectedArrival"]:
            raise AssertionError(f"{city}/{case['name']}: changed arrival")
        legs = result["legs"]
        lines = [leg["publicLine"] for leg in legs]
        if lines != case["expectedLines"]:
            raise AssertionError(f"{city}/{case['name']}: wrong lines {lines}")
        trips = [leg["tripOccurrence"].split(":")[1] for leg in legs]
        if trips != case["expectedTrips"]:
            raise AssertionError(f"{city}/{case['name']}: wrong trip occurrences")
        if "expectedTransferStop" in case:
            if legs[0]["to"] != case["expectedTransferStop"] or (
                    legs[1]["from"] != case["expectedTransferStop"]):
                raise AssertionError(f"{city}/{case['name']}: wrong transfer stop")
        tested.append({
            "case": case["name"], "status": "PASS_WITHIN_FEED",
            "lines": lines, "arrivalSecondsFromServiceAnchor": result["arrival"],
        })
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA temp_store=MEMORY")
    populate_sqlite(s, db)
    mib = (db.execute("PRAGMA page_count").fetchone()[0] *
           db.execute("PRAGMA page_size").fetchone()[0] / (1024 ** 2))
    db.close()
    return {
        "city":city, "state":"RESEARCH_ONLY",
        "sourceSHA256":s.source_sha256,
        "busConnections":len(s.connections),
        "sqliteMiB":round(mib,2),
        "passedCases":len(tested), "cases":tested,
        "elapsedSeconds":round(time.monotonic()-t0,2),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--west", required=True)
    p.add_argument("--south", required=True)
    args = p.parse_args(argv)
    for city, path in (("Coventry",args.west),("Bristol",args.south)):
        print(json.dumps(check_city(city,path)),flush=True)


if __name__ == "__main__":
    main()
