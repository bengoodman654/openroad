"""Check evidence manifests exist and never assert passenger-ready or production acceptance."""
import json
import unittest
from pathlib import Path
from bods_metadata import verify_source_identity
ROOT=Path(__file__).resolve().parents[2]/"docs/public-transport-v2/fixtures"

class OfficialEvidenceManifest(unittest.TestCase):
    def test_coventry_source_is_pinned_and_matches_reference_services(self):
        m=json.loads((ROOT/"official_coventry_txc_manifest.json").read_text())
        self.assertEqual(m["operator_noc"],"TCVW")
        self.assertEqual(len(m["download_sha256"]),64)
        self.assertEqual(m["archive_members"],m["xml_files_streamed"])
        self.assertEqual(set(m["matches"]),{"9","11","12X"})
        for number,files in m["matches"].items():
            self.assertEqual(len(files),2,number)
            self.assertTrue(all(x["vehicle_journeys"]>0 for x in files))
        self.assertEqual(m["production_acceptance_cases_passed"],0)

    def test_bristol_metadata_not_pretended_complete(self):
        m=json.loads((ROOT/"official_bristol_candidates.json").read_text())
        self.assertEqual(m["operator_noc"],"FBRI")
        self.assertEqual(m["target_service"],"75")
        self.assertGreater(m["observed_result"]["total_record_count"],m["observed_result"]["records_on_first_page"])
        self.assertFalse(m["observed_result"]["pagination_complete"])
        self.assertEqual(m["downloaded_files"],0)
        self.assertEqual(m["production_acceptance_cases_passed"],0)
    def test_lookalike_services_in_wrong_cities_are_rejected(self):
        evidence=json.loads((ROOT/"official_bristol_negative_sources.json").read_text())
        self.assertEqual(len(evidence["observed_mismatches"]),3)
        for case in evidence["observed_mismatches"]:
            self.assertNotEqual(case["member_noc"],"FBRI")
            self.assertIn("75",case["member_lines"])
            self.assertEqual(
                verify_source_identity("FBRI","75",[case["member_noc"]],case["member_lines"]),
                "REJECT_WRONG_OPERATOR")
            self.assertEqual(len(case["sha256"]),64)
        self.assertEqual(evidence["production_acceptance_cases_passed"],0)

    def test_correct_operator_and_line_still_require_geography_and_calendar(self):
        self.assertEqual(
            verify_source_identity("FBRI","75",["FBRI"],["75"]),
            "NEEDS_STOP_AND_GEOGRAPHY_EVIDENCE")
        self.assertEqual(
            verify_source_identity("FBRI","75",["FBRI"],["75"],True),
            "CANDIDATE_NEEDS_CALENDAR_AND_TRIP_VALIDATION")

if __name__=="__main__":unittest.main()
