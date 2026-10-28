"""Assert staged v0.6.31 patch is non-destructive and narrowly scoped."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from pilot.stage_pt_v2_android import stage, replace_one

class AndroidStageTests(unittest.TestCase):
    def test_stage_modifies_only_ui_files_and_never_original_archive(self):
        baseline=Path("OpenRoad-v0.6.31-source.zip")
        size=baseline.stat().st_size
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"staged.zip"
            stage(baseline,out)
            with ZipFile(baseline) as before, ZipFile(out) as after:
                self.assertEqual(before.namelist(),after.namelist())
                changed=[n for n in before.namelist()
                         if before.read(n)!=after.read(n)]
                self.assertEqual(sorted(n.rsplit("/",1)[-1] for n in changed),
                                 ["OpenRoadServerClient.java","TransitClient.java","app.js","index.html"])
                js=after.read(next(n for n in after.namelist()
                    if n.endswith("/app/src/main/assets/app.js"))).decode()
                html=after.read(next(n for n in after.namelist()
                    if n.endswith("/app/src/main/assets/index.html"))).decode()
                self.assertIn("openroadPtXAction()",js)
                self.assertIn("openroadPtBackOneScreen()",js)
                self.assertIn("No journey was changed.",js)
                self.assertIn("data.routes.some",js)
                self.assertIn('id="ptBackBtn"',html)
                client=after.read(next(n for n in after.namelist()
                    if n.endswith("/OpenRoadServerClient.java"))).decode()
                transit=after.read(next(n for n in after.namelist()
                    if n.endswith("/TransitClient.java"))).decode()
                for term in ("ptV2Issue(","ptV2Route(","ptV2Cancel(","ptV2Status("):
                    self.assertIn(term,client)
                self.assertIn("ptV2Research",transit)
                self.assertIn("ACTIVE_V2.getAndSet(null)",transit)
                self.assertIn("routeWorkCancelled(generation)",transit)
                self.assertIn("PT v2 research does not yet support added stops.",transit)
        self.assertEqual(baseline.stat().st_size,size)

    def test_unexpected_source_rejected(self):
        with self.assertRaisesRegex(ValueError,"expected exactly one"):
            replace_one("unchanged","absent","new")
