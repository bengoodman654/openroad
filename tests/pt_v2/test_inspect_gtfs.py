"""Offline adapter contract: real published route facts, synthetic GTFS schedules, no upstream calls."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from datetime import date
from test_bristol_coventry import REFERENCE, archive
from gtfs_fixture_adapter import GTFSFixture
from inspect_gtfs import inspect

class OfflineImportInspection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.zip=Path(self.temp.name)/"synthetic.zip"
        archive(self.zip)
        self.ref=json.loads(REFERENCE.read_text(encoding="utf-8"))
    def tearDown(self):self.temp.cleanup()

    def test_date_scoped_candidate_listing_not_falsely_verified(self):
        data=inspect(GTFSFixture.open(self.zip),self.ref,date(2026,10,24))
        by_id={x["case"]:x for x in data}
        self.assertEqual(by_id["BRI-75"]["evaluation"],"CANDIDATE_REVIEW_REQUIRED")
        self.assertTrue(by_id["BRI-75"]["candidates"][0]["possible_endpoint_match"])
        self.assertEqual(by_id["COV-11"]["candidate_count"],2)
        self.assertEqual(by_id["COV-12X"]["candidate_count"],1)
        self.assertEqual(by_id["COV-9"]["evaluation"],"NO_MATCH_IN_SUPPLIED_ARCHIVE")
        self.assertEqual(by_id["COV-9"]["candidate_count"],0)

    def test_cli_writes_evidence_scoped_report_without_network(self):
        output=Path(self.temp.name)/"report.json"
        command=[sys.executable,str(Path(__file__).with_name("inspect_gtfs.py")),
                 "--archive",str(self.zip),"--date","2026-10-24",
                 "--source-url","https://example.org/SYNTHETIC-only",
                 "--reference",str(REFERENCE),"--output",str(output)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["real_integration_cases_passed"],0)
        self.assertEqual(len(report["archive_sha256"]),64)
        self.assertEqual(report["service_date"],"2026-10-24")
        self.assertEqual(report["kind"],"GTFS_IMPORT_INSPECTION_NOT_PRODUCTION_ACCEPTANCE")

    def test_cli_rejects_non_https_provenance(self):
        command=[sys.executable,str(Path(__file__).with_name("inspect_gtfs.py")),
                 "--archive",str(self.zip),"--date","2026-10-24",
                 "--source-url","http://untrusted.invalid"]
        result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("HTTPS",result.stderr)

    def test_cli_rejects_unbounded_memory_profile(self):
        command=[sys.executable,str(Path(__file__).with_name("inspect_gtfs.py")),
                 "--archive",str(self.zip),"--date","2026-10-24",
                 "--source-url","https://example.org","--max-mib","1000"]
        result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("256",result.stderr)

if __name__=="__main__":unittest.main()
