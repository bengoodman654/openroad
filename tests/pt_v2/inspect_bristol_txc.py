"""One bounded official Bristol BODS dataset inspection on a temporary GitHub runner.

Operator service data only: no JustHostMe workload, no claim of verified departures.
"""
from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from zipfile import ZipFile
import json
from txc_stream import scan,MAX_MEMBER

SOURCE="https://data.bus-data.dft.gov.uk/timetable/dataset/2154/download/"
MAX_ZIP=6*1024*1024
MAX_STREAM_TOTAL=150*1024*1024

def get():
    data=[];size=0;digest=sha256()
    with urlopen(Request(SOURCE,headers={"User-Agent":"OpenRoad-PTv2-Bristol-Bounded-TXC/1.0"}),timeout=30) as r:
        p=urlsplit(r.geturl())
        if p.scheme!="https" or p.hostname!="data.bus-data.dft.gov.uk":raise ValueError("Unexpected download host")
        while True:
            buf=r.read(1024*1024)
            if not buf:break
            size+=len(buf)
            if size>MAX_ZIP:raise ValueError("Bristol download exceeds 6 MiB cap")
            data.append(buf);digest.update(buf)
    return BytesIO(b"".join(data)),size,digest.hexdigest()

def inspect(zfile,size,digest):
    with ZipFile(zfile) as z:
        items=[x for x in z.infolist() if not x.is_dir()]
        total=sum(i.file_size for i in items)
        if len(items)>250 or total>MAX_STREAM_TOTAL:
            print(json.dumps({"status":"BLOCKED_BY_MANIFEST_RESOURCE_GATE","archive_members":len(items),
                              "uncompressed_bytes":total,"compressed_bytes":size,"sha256":digest}))
            return 2
        nocs=Counter();found=[];routes=0;trips=0
        for info in items:
            filename=PurePosixPath(info.filename)
            if info.filename.startswith("/") or ".." in filename.parts or not info.filename.lower().endswith(".xml"):
                raise ValueError("Unexpected/unsafe member path")
            if info.file_size>MAX_MEMBER:raise ValueError("XML member too large for bounded stream")
            with z.open(info) as handle:
                item=scan(handle)
            if item["bytes"]!=info.file_size:raise ValueError("Unexpected decompressed size")
            nocs.update(item["nocs"])
            routes+=item["counts"].get("Route",0)
            trips+=item["counts"].get("VehicleJourney",0)
            if "75" in item["lines"]:
                found.append({"member":filename.name[:110],
                              "line_names":item["lines"][:8],
                              "vehicle_journeys":item["counts"].get("VehicleJourney",0),
                              "service_code_count":item["service_codes"]})
        print(json.dumps({
            "source":"Official BODS Bristol dataset 2154",
            "dataset_id":"2154", "sha256":digest, "download_bytes":size,
            "xml_members":len(items),"expanded_bytes":total,
            "operator_codes":dict(nocs),"matching_line_75_files":found,
            "routes_observed":routes,"vehicle_journeys_observed":trips,
            "date_specific_departures_verified":False,
            "production_acceptance_cases_passed":0
        },sort_keys=True))
        return 0

if __name__=="__main__":
    args=get()
    raise SystemExit(inspect(*args))
