"""Source-pinned CLI worker tests on a tiny isolated GTFS index."""
import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from maintenance.gtfs_refresh.test_query_sqlite import IndexRoutingTests

SCRIPT=Path(__file__).with_name("city_planner_cli.py")

class CLIContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=IndexRoutingTests("test_refuse_unsupported_date")
        self.fixture.setUp()
        self.path=self.fixture.db
        with sqlite3.connect(self.path) as db:
            self.sha=json.loads(db.execute(
                "SELECT value FROM info WHERE name='sourceArchiveSha256'"
            ).fetchone()[0])
        self.query={
            "from":{"lat":51.4545,"lon":-2.5879},
            "to":{"lat":51.46,"lon":-2.595},
            "serviceDate":"2026-10-29",
            "earliestSec":8*3600+40*60,
            "maxWalkMetres":180,
        }

    def tearDown(self):self.fixture.tearDown()

    def invoke(self,request=None,sha=None):
        r=subprocess.run([
            sys.executable,"-B",str(SCRIPT),
            "--index",str(self.path),
            "--region","south_west",
            "--source-sha",sha or self.sha
        ],input=json.dumps(self.query if request is None else request),
            capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertLess(len(r.stdout),131072)
        return json.loads(r.stdout)

    def test_real_fixture_journey_not_selectable(self):
        response=self.invoke()
        self.assertEqual(response["outcome"],"OK",response)
        self.assertEqual(response["snapshotId"],self.sha)
        self.assertTrue(response["results"])
        self.assertTrue(all(x["researchOnly"] and
                            not x["selectable"] for x in response["results"]))

    def test_untrusted_source_digest_cannot_return_journey(self):
        result=self.invoke(sha="a"*64)
        self.assertEqual(result["outcome"],"PROVIDER_UNAVAILABLE")
        self.assertFalse(result["results"])

    def test_boolean_coordinates_rejected_without_private_trace(self):
        q={**self.query,"from":{"lat":True,"lon":-2.5879}}
        result=self.invoke(request=q)
        self.assertEqual(result["outcome"],"INPUT_INVALID")
        self.assertFalse(result["results"])
        self.assertNotIn(str(self.path),json.dumps(result))

    def test_unsupported_excessive_walking_disallowed(self):
        q={**self.query,"maxWalkMetres":9999}
        self.assertEqual(self.invoke(request=q)["outcome"],"INPUT_INVALID")

if __name__=="__main__":unittest.main()
