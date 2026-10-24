"""Read all 38 known official Coventry TXC members using bounded streaming XML.

Heavy work runs ONLY on disposable GitHub runner. Production host unchanged.
"""
from collections import Counter
from pathlib import PurePosixPath
from zipfile import ZipFile
import json
from inspect_txc_20442 import get
from txc_stream import scan,MAX_MEMBER
EXPECTED_SHA="5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0"
MAX_ARCHIVE_EXPANDED=350*1024*1024
MAX_MEMBERS=50
TARGET_LINES={"9","11","12X"}
def main():
    zipbuf,zip_size,sha=get()
    if sha!=EXPECTED_SHA:raise ValueError("Published ZIP changed; inspect and reapprove snapshot before full streaming")
    found={key:[] for key in TARGET_LINES}
    noc_counts=Counter()
    routes=0;trips=0
    with ZipFile(zipbuf) as z:
        infos=[m for m in z.infolist() if not m.is_dir()]
        if not 1<=len(infos)<=MAX_MEMBERS:raise ValueError("Unexpected archive membership count")
        total=sum(m.file_size for m in infos)
        if total>MAX_ARCHIVE_EXPANDED:raise ValueError("Archive exceeds 350 MiB off-host streaming budget")
        for info in infos:
            name=PurePosixPath(info.filename)
            if info.filename.startswith("/") or ".." in name.parts or not info.filename.lower().endswith(".xml"):
                raise ValueError("Unexpected archive file or unsafe path")
            if info.file_size>MAX_MEMBER:raise ValueError("One member exceeds 40 MiB streaming cap")
            with z.open(info) as part:
                result=scan(part,limit=MAX_MEMBER)
            if result["bytes"]!=info.file_size:raise ValueError("Archive stream size does not match manifest")
            routes+=result["counts"].get("Route",0)
            trips+=result["counts"].get("VehicleJourney",0)
            noc_counts.update(result["nocs"])
            for line in TARGET_LINES.intersection(result["lines"]):
                found[line].append({
                    "file":name.name[:110],
                    "vehicle_journeys_in_file":result["counts"].get("VehicleJourney",0),
                    "service_code_count_in_file":result["service_codes"],
                })
    print(json.dumps({
        "source":"BODS official operator-scoped dataset 20442",
        "archive_sha256":sha,"compressed_bytes":zip_size,
        "total_uncompressed_streamed_bytes":total,
        "xml_files_scanned":len(infos),
        "noc_files":dict(noc_counts),
        "line_matched_files":{x:found[x] for x in sorted(TARGET_LINES)},
        "routes_observed":routes,"vehicle_journeys_observed":trips,
        "method":"Full streaming XML metadata inspection; not GTFS calendar/stop geometry conversion",
        "production_acceptance_cases_passed":0
    },sort_keys=True))
if __name__=="__main__":main()
