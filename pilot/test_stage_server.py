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
                self.assertEqual(len(names)-len(base.namelist()),2)
                for name in base.namelist():
                    self.assertEqual(base.read(name),staged.read(name),
                                     "Original server file changed: "+name)
                self.assertFalse(any("/public/api/v2/" in n for n in names))
