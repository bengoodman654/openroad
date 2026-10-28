"""Copy the reference PHP cancellation libraries into an isolated v0.2.5 ZIP.

The original server archive and public endpoints remain byte-for-byte intact.
"""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

def stage_server(source, destination):
    libfiles=("php_v2_cancellation.php", "php_v2_device_adapter.php",
              "php_v2_route_worker.php")
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
        # Patch ONLY the staged router copy, never the original v1 archive.
        # Existing callers supply no cancelCheck and retain current behaviour.
        router_text=z.read(router[0]).decode("utf-8")
        start=router_text.index("function openroad_plan_bus(")
        stop=router_text.index("\nfunction or_normalise_line(",start)
        body=router_text[start:stop]
        signature="array $settings=[]): array {"
        if body.count(signature)!=1:
            raise ValueError("Unknown v1 router function signature")
        body=body.replace(signature,
                          "array $settings=[],?callable $cancelCheck=null): array {")
        checks=body.count("or_route_check_budget();")
        if checks < 4:
            raise ValueError("Insufficient original routing checkpoints")
        body=body.replace("or_route_check_budget();","$checkCancellation();")
        first="$started=microtime(true);"
        if body.count(first)!=1:
            raise ValueError("Unexpected planner start marker")
        body=body.replace(first,
            """$checkCancellation=static function()use($cancelCheck):void{
                if($cancelCheck!==null && $cancelCheck())
                    throw new RuntimeException('REQUEST_CANCELLED');
                or_route_check_budget();
            };
            $checkCancellation();""" + first)
        inserts[router[0]]=(router_text[:start]+body+router_text[stop:]).encode("utf-8")
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(destination,"w",ZIP_DEFLATED,compresslevel=6) as out:
            for info in z.infolist():
                data=inserts.pop(info.filename,z.read(info.filename))
                out.writestr(info,data)
            for filename,data in inserts.items():out.writestr(filename,data)
    print("STAGED_PHP_LIBRARIES_ONLY", destination, flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="OpenRoad-Transport-Server-v0.2.5-source.zip")
    p.add_argument("--output",required=True)
    a=p.parse_args();stage_server(a.source,a.output)
