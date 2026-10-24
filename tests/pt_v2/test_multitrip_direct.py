"""Offline multi-trip direct routing contracts. Synthetic duplicates are explicitly marked."""
import copy
import json
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from coventry_11_multitrip import UnsupportedTXC
from multitrip_direct import validate,direct_options,PIN

DATA=Path(__file__).resolve().parents[2]/"docs/public-transport-v2/fixtures"
ZONE=ZoneInfo("Europe/London")

def synthetic():
    src=json.loads((DATA/"official_coventry_11_friday_2026-10-23_candidate.json").read_text())
    trip=copy.deepcopy(src["journey"])
    return {"kind":"REAL_TXC_MULTITRIP_OFFLINE_CANDIDATES","operator_noc":"TCVW",
            "line":"11","service_code":"PD0001111:813",
            "source_dataset":"20442","source_zip_sha256":PIN,
            "source_xml_member":src["source_xml_member"],
            "service_date":"2026-10-23","time_zone":"Europe/London","trips":[trip]}

class MultiTripDirectContracts(unittest.TestCase):
    def test_known_real_source_trip_remains_available(self):
        a=synthetic()
        x=direct_options(a,"43000065301","43000005010",datetime(2026,10,23,5,40,tzinfo=ZONE))
        self.assertEqual(x["outcome"],"OK")
        self.assertEqual(x["results"][0]["departure"],"2026-10-23T05:55:00+01:00")
        self.assertEqual(x["results"][0]["arrival"],"2026-10-23T06:21:00+01:00")

    def test_reverse_direction_missing_and_missed_departures(self):
        a=synthetic()
        q=datetime(2026,10,23,5,40,tzinfo=ZONE)
        self.assertEqual(direct_options(a,"43000005010","43000065301",q)["outcome"],"NO_JOURNEY")
        self.assertEqual(direct_options(a,"X","43000005010",q)["outcome"],"NO_JOURNEY")
        later=datetime(2026,10,23,5,56,tzinfo=ZONE)
        self.assertEqual(direct_options(a,"43000065301","43000005010",later)["outcome"],"NO_JOURNEY")

    def test_synthetic_second_trip_options_are_sorted_and_bounded(self):
        a=synthetic()
        # A synthetic copy is used to test ordering, not to assert a real second departure.
        second=copy.deepcopy(a["trips"][0]);second["journey_code"]="SYNTHETIC_NEXT"
        second["published_departure_time"]="06:10:00"
        a["trips"].append(second)
        q=datetime(2026,10,23,5,40,tzinfo=ZONE)
        r=direct_options(a,"43000065301","43000005010",q)
        self.assertEqual(len(r["results"]),2)
        self.assertLess(r["results"][0]["arrival"],r["results"][1]["arrival"])
        self.assertEqual(r["results"][1]["departure"],"2026-10-23T06:10:00+01:00")

    def test_missing_approval_or_mixed_source_fails(self):
        a=synthetic()
        a["source_zip_sha256"]="0"*64
        with self.assertRaises(UnsupportedTXC):validate(a)
        a=synthetic();a["operator_noc"]="FECS"
        with self.assertRaises(UnsupportedTXC):validate(a)

    def test_duplicate_trip_identifier_fails(self):
        a=synthetic();a["trips"].append(copy.deepcopy(a["trips"][0]))
        with self.assertRaises(UnsupportedTXC):validate(a)

    def test_invalid_boarding_and_alighting_fail(self):
        a=synthetic();a["trips"][0]["stops"][0]["activity"]="setDown"
        q=datetime(2026,10,23,5,40,tzinfo=ZONE)
        self.assertEqual(direct_options(a,"43000065301","43000005010",q)["outcome"],"NO_JOURNEY")

    def test_no_autumn_clock_change_claim(self):
        a=synthetic();a["service_date"]="2026-10-25"
        q=datetime(2026,10,25,5,40,tzinfo=ZONE)
        self.assertEqual(direct_options(a,"43000065301","43000005010",q)["outcome"],
                         "UNSUPPORTED_CALENDAR_TIME_TRANSITION")

    def test_naive_date_and_invalid_request_limits(self):
        a=synthetic()
        with self.assertRaises(UnsupportedTXC):direct_options(a,"A","B",datetime(2026,10,23,5,0))
        with self.assertRaises(UnsupportedTXC):direct_options(a,"A","B",datetime(2026,10,23,5,0,tzinfo=ZONE),6)

if __name__=="__main__":unittest.main()
