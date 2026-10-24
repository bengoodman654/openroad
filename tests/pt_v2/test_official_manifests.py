"""Check evidence manifests exist and never assert passenger-ready or production acceptance."""
import json
import unittest
from pathlib import Path
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
if __name__=="__main__":unittest.main()
