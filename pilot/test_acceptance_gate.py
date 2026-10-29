import json
import unittest
from pilot.acceptance_gate import MANIFEST,acceptance_report

class AcceptanceGateTests(unittest.TestCase):
    def test_105_named_cases_and_fifteen_workstreams(self):
        cases=json.loads(MANIFEST.read_text())
        self.assertEqual(len(cases),105)
        self.assertEqual(len({x["id"] for x in cases}),105)
        self.assertEqual(len({x["group"] for x in cases}),15)
        self.assertEqual({x["status"] for x in cases},
                         {"PENDING_PRODUCTION_ACCEPTANCE"})
    def test_no_automatic_research_promotion(self):
        result=acceptance_report()
        self.assertEqual(result["accepted"],0)
        self.assertFalse(result["releaseReady"])
    def test_synthetic_unit_test_not_accepted(self):
        result=acceptance_report({"PT-001":{
            "status":"PASS","deviceBuild":"0.6.32",
            "sourceSnapshot":"test",
            "verificationMethod":"UNIT_TEST",
            "evidenceURI":"https://example.invalid",
            "reviewedBy":"fixture"}})
        self.assertEqual(result["accepted"],0)
    def test_one_certified_case_not_full_release(self):
        result=acceptance_report({"PT-001":{
            "status":"PASS","deviceBuild":"0.6.32",
            "sourceSnapshot":"verified-feed",
            "verificationMethod":"INDEPENDENT_END_TO_END",
            "evidenceURI":"https://github.com/example/evidence",
            "reviewedBy":"independent reviewer"}})
        self.assertEqual(result["accepted"],1)
        self.assertFalse(result["releaseReady"])
