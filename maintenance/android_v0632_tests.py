from pathlib import Path
from zipfile import ZipFile
import subprocess,tempfile,unittest
ZIP=Path("OpenRoad-v0.6.31-source.zip")
PATCH=Path("maintenance/android-v0.6.32/patch.py")
class ReleaseTests(unittest.TestCase):
    def test_source_only_expected_files_change(self):
        with tempfile.TemporaryDirectory() as td:
            with ZipFile(ZIP) as z:z.extractall(td)
            root=next(p for p in Path(td).iterdir() if p.is_dir())
            before={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            subprocess.run(["python3",str(PATCH.resolve()),str(root)],check=True,
                           capture_output=True,text=True)
            after={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(set(before),set(after))
            self.assertEqual({str(p) for p in before if before[p]!=after[p]},{
              "app/src/main/assets/app.js","app/src/main/assets/index.html",
              "app/build.gradle","app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java",
              "validate.sh"})
            gradle=(root/"app/build.gradle").read_text()
            self.assertIn("versionCode 92",gradle)
            self.assertIn("versionCode 92",(root/"validate.sh").read_text())
            self.assertIn("0.6.32",gradle)
            js=(root/"app/src/main/assets/app.js").read_text()
            self.assertIn("openroadPtXAction()",js)
            self.assertNotIn("ptV2Research",js)
            with self.assertRaises(subprocess.CalledProcessError):
                subprocess.run(["python3",str(PATCH.resolve()),str(root)],
                               check=True,capture_output=True,text=True)
