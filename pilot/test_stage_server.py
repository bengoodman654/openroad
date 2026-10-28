import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from pilot.stage_pt_v2_server import stage_server

class StageServerTest(unittest.TestCase):
    def test_existing_public_server_endpoints_untouched(self):
        original=Path("OpenRoad-Transport-Server-v0.2.5-source.zip")
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"server-staged.zip"
            stage_server(original,dest)
            with ZipFile(original) as base,ZipFile(dest) as staged:
                names=staged.namelist()
                self.assertEqual(set(base.namelist()),
                    set(n for n in names if n in base.namelist()))
                self.assertEqual(len(names)-len(base.namelist()),5)
                changed=[]
                for name in base.namelist():
                    if base.read(name)!=staged.read(name):
                        changed.append(name)
                self.assertEqual(len(changed),1)
                self.assertTrue(changed[0].endswith("/private/lib/router.php"))
                router_code=staged.read(changed[0]).decode()
                self.assertIn("?callable $cancelCheck=null",router_code)
                self.assertIn("$checkCancellation();",router_code)
                endpoints=[n for n in names if "/public/api/v2/" in n]
                self.assertEqual(len(endpoints),1)
                self.assertTrue(endpoints[0].endswith("/task.php"))
                body=staged.read(endpoints[0]).decode()
                self.assertIn("openroad_require_signed($db,$body)",body)
                self.assertIn("PT_V2_NOT_CONFIGURED",body)
                self.assertIn("ptv2_dispatch",body)
