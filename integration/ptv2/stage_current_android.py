from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
from integration.ptv2.android_java_patch import patch_server, patch_transit

def stage(source, output):
    with ZipFile(source) as z:
        names = z.namelist()
        def find(suffix):
            found=[p for p in names if p.endswith("/"+suffix)]
            if len(found)!=1:
                raise RuntimeError("Unsupported source layout: "+suffix)
            return found[0]
        client=find("app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java")
        transit=find("app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java")
        patched={client:patch_server(z.read(client).decode()).encode(),
                 transit:patch_transit(z.read(transit).decode()).encode()}
        app=find("app/src/main/assets/app.js")
        gradle=find("app/build.gradle")
        if b"0.6.32" not in z.read(gradle):
            raise RuntimeError("Wrong Android baseline")
        if b"ptV2Research" in z.read(app):
            raise RuntimeError("Research mode exposed in UI")
        output=Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,"w",ZIP_DEFLATED) as out:
            for info in z.infolist():
                out.writestr(info,patched.get(info.filename,z.read(info.filename)))
    print("CURRENT_ANDROID_0632_SIGNED_V2_JAVA_STAGE_OK")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="OpenRoad-v0.6.32-source.zip")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    stage(a.source,a.output)
