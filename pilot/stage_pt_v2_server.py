"""Copy the reference PHP cancellation libraries into an isolated v0.2.5 ZIP.

The original server archive and public endpoints remain byte-for-byte intact.
"""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

def stage_server(source, destination):
    libfiles=("php_v2_cancellation.php", "php_v2_device_adapter.php")
    with ZipFile(source) as z:
        original=z.namelist()
        router=[n for n in original if n.endswith("/private/lib/router.php")]
        if len(router)!=1: raise ValueError("Unexpected server ZIP structure")
        root=router[0][:-len("private/lib/router.php")]
        inserts={}
        for file in libfiles:
            full=root+"private/lib/"+file
            if full in original:raise ValueError("Research library already exists")
            inserts[full]=(Path(__file__).parent/file).read_bytes()
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(destination,"w",ZIP_DEFLATED,compresslevel=6) as out:
            for info in z.infolist():out.writestr(info,z.read(info.filename))
            for filename,data in inserts.items():out.writestr(filename,data)
    print("STAGED_PHP_LIBRARIES_ONLY", destination, flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="OpenRoad-Transport-Server-v0.2.5-source.zip")
    p.add_argument("--output",required=True)
    a=p.parse_args();stage_server(a.source,a.output)
