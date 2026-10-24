"""First source-derived offline routing checks, with independently displayed timetable anchors.

These DO NOT test any production Android/server journey-planning endpoint.
"""
import copy
import json
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from real_fixture_direct import FixtureError,validate,plan_direct,local_datetime

PATH=Path(__file__).resolve().parents[2]/"docs/public-transport-v2/fixtures"
ZONE=ZoneInfo("Europe/London")

class Coventry11SourceRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=json.loads((PATH/"official_coventry_11_friday_2026-10-23_candidate.json").read_text(encoding="utf-8"))
        cls.anchor=json.loads((PATH/"official_coventry_11_external_timepoints.json").read_text(encoding="utf-8"))

    def test_real_fixture_source_and_calendar_are_explicitly_scoped(self):
        j=validate(self.f)
        self.assertEqual(self.f["source_dataset"],"20442")
        self.assertEqual(self.f["service_date"],"2026-10-23")
        self.assertEqual(self.f["operator_noc"],"TCVW")
        self.assertEqual(len(self.f["source_zip_sha256"]),64)
        self.assertEqual(j["journey_code"],"VJ136")
        self.assertEqual(len(j["stops"]),26)
        self.assertEqual(j["stops"][0]["activity"],"pickUp")
        self.assertEqual(j["stops"][-1]["activity"],"setDown")

    def test_external_timetable_anchors_match_source_derived_intermediate_times(self):
        # Bus Times timetable (dated 2026-10-23), separate rendering from our converter;
        # may ultimately share the same underlying BODS publication.
        self.assertEqual(self.anchor["service_date"],self.f["service_date"])
        lookup={s["stop_ref"]:s for s in self.f["journey"]["stops"]}
        for event in self.anchor["stop_times"]:
            s=lookup[event["stop_ref"]]
            t=local_datetime(self.f,s["departure_offset_seconds"])
            self.assertEqual(t.strftime("%H:%M"),event["time"],event["name"])

    def test_real_source_direct_journey_university_to_pool_meadow(self):
        r=plan_direct(self.f,"43000065301","43000005010",datetime(2026,10,23,5,40,tzinfo=ZONE))
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["departure"],"2026-10-23T05:55:00+01:00")
        self.assertEqual(r["arrival"],"2026-10-23T06:21:00+01:00")
        self.assertEqual(r["intermediate_stops"],24)
        self.assertTrue(r["trip_occurrence_id"].startswith("TCVW:PD0001111:813:"))

    def test_board_at_scarman_road_not_only_origin(self):
        r=plan_direct(self.f,"43001317102","43000005010",datetime(2026,10,23,5,55,tzinfo=ZONE))
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["departure"],"2026-10-23T05:56:00+01:00")

    def test_reject_reverse_direction_and_unknown_stop(self):
        q=datetime(2026,10,23,5,30,tzinfo=ZONE)
        self.assertEqual(plan_direct(self.f,"43000005010","43000065301",q)["outcome"],"NO_JOURNEY")
        self.assertEqual(plan_direct(self.f,"unknown","43000005010",q)["reason"],"STOP_NOT_BOARDABLE_OR_ALIGHTABLE")

    def test_no_trip_after_published_departure_for_same_origin(self):
        q=datetime(2026,10,23,5,56,tzinfo=ZONE)
        self.assertEqual(plan_direct(self.f,"43000065301","43000005010",q)["outcome"],"NO_JOURNEY")

    def test_boarding_and_alighting_constraints_fail_closed(self):
        altered=copy.deepcopy(self.f)
        altered["journey"]["stops"][-1]["activity"]="pass"
        q=datetime(2026,10,23,5,30,tzinfo=ZONE)
        self.assertEqual(plan_direct(altered,"43000065301","43000005010",q)["outcome"],"NO_JOURNEY")

    def test_reject_different_unverified_date(self):
        altered=copy.deepcopy(self.f);altered["service_date"]="2026-10-24";altered["weekday"]="Saturday"
        with self.assertRaises(FixtureError):validate(altered)

    def test_reject_bad_operator_even_if_service_number_identical(self):
        altered=copy.deepcopy(self.f);altered["operator_noc"]="FECS"
        with self.assertRaises(FixtureError):validate(altered)

    def test_require_monotonic_stops_to_prevent_impossible_journeys(self):
        altered=copy.deepcopy(self.f);altered["journey"]["stops"][4]["arrival_offset_seconds"]=-1
        with self.assertRaises(FixtureError):validate(altered)

    def test_rejects_archive_or_member_substitution(self):
        changed=copy.deepcopy(self.f)
        changed["source_zip_sha256"]="0"*64
        with self.assertRaises(FixtureError):validate(changed)
        changed=copy.deepcopy(self.f)
        changed["source_xml_member"]="other.xml"
        with self.assertRaises(FixtureError):validate(changed)

    def test_rejects_invalid_stop_activity(self):
        changed=copy.deepcopy(self.f)
        changed["journey"]["stops"][0]["activity"]="unknown"
        with self.assertRaises(FixtureError):validate(changed)

    def test_timezone_aware_request_mandatory(self):
        with self.assertRaises(FixtureError):
            plan_direct(self.f,"43000065301","43000005010",datetime(2026,10,23,5,40))

if __name__=="__main__":unittest.main()
