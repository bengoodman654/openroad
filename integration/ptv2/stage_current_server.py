#!/usr/bin/env python3
"""Build research-only PT v2 on top of the EXACT current v0.2.9 router.
This script never writes to the tracked source archive or deploys anything.
"""
from __future__ import annotations
import argparse
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

LIBS=("php_v2_cancellation.php","php_v2_device_adapter.php",
      "php_v2_route_worker.php","php_v2_protocol.php")
def stage(source: Path, output: Path):
    root_repo=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)
        with ZipFile(source) as z:
            z.extractall(work)
            originals={p.relative_to(work):p.read_bytes()
                       for p in work.rglob("*") if p.is_file()}
        matches=list(work.rglob("private/lib/router.php"))
        if len(matches)!=1:raise RuntimeError("Ambiguous real v0.2.5 router")
        router=matches[0]
        for script in ("patch_router.py","patch_router_v029.py"):
            subprocess.run(["python3",str(root_repo/"maintenance/pt-sql-timeout"/script),
                            str(router)],check=True)
        current=router.read_text(encoding="utf-8")
        assert "function or_active_boardings(" in current
        assert "function or_active_arrivals(" in current
        assert "function or_second_leg_candidates(" in current
        first=current.index("function openroad_plan_bus(")
        last=current.index("\nfunction or_normalise_line(",first)
        body=current[first:last]
        sig="array $settings=[]): array {"
        if body.count(sig)!=1:raise RuntimeError("Current router signature changed")
        body=body.replace(sig,"array $settings=[],?callable $cancelCheck=null): array {")
        probe="or_route_check_budget();"
        if body.count(probe)<4:raise RuntimeError("Insufficient safe cancellation checkpoints")
        body=body.replace(probe,"$checkCancellation();")
        marker="$started=microtime(true);"
        if body.count(marker)!=1:raise RuntimeError("Planner deadline anchor changed")
        body=body.replace(marker,
            """$checkCancellation=static function()use($cancelCheck):void{
                if($cancelCheck!==null && $cancelCheck())
                    throw new RuntimeException('REQUEST_CANCELLED');
                or_route_check_budget();
            };
            if($cancelCheck!==null && $cancelCheck())
                throw new RuntimeException('REQUEST_CANCELLED');"""+marker)
        router.write_text(current[:first]+body+current[last:],encoding="utf-8")
        private=router.parent
        for filename in LIBS:
            target=private/filename
            if target.exists():raise RuntimeError("Research file already present: "+filename)
            target.write_bytes((Path(__file__).parent/filename).read_bytes())
        endpoint=router.parents[2]/"public/api/v2/task.php"
        if endpoint.exists():raise RuntimeError("Research endpoint already present")
        endpoint.parent.mkdir(parents=True,exist_ok=True)
        endpoint.write_bytes((Path(__file__).parent/"php_v2_endpoint.php").read_bytes())
        after={p.relative_to(work):p.read_bytes() for p in work.rglob("*") if p.is_file()}
        changed={str(p) for p in originals if originals[p]!=after[p]}
        expected={str(router.relative_to(work))}
        if changed!=expected:raise RuntimeError("Unexpected original files modified: "+str(changed))
        additional=set(after)-set(originals)
        if len(additional)!=5:raise RuntimeError("Unexpected new server file count")
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,"w",ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(after):
                z.writestr(str(p),after[p])
        print("CURRENT_V029_STAGED_RESEARCH_ROUTER_OK")
        print("CHANGED_ORIGINAL_FILES="+str(len(changed)))
        print("ADDED_RESEARCH_FILES="+str(len(additional)))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="OpenRoad-Transport-Server-v0.2.5-source.zip")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    stage(Path(a.source),Path(a.output))
