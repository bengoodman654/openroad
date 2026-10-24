"""One bounded official Bristol BODS dataset inspection on a temporary GitHub runner.

Candidate source data only: do not infer Bristol from a matching route number.
"""
import argparse
import re
from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from zipfile import ZipFile
import json
from txc_stream import scan,MAX_MEMBER

MAX_ZIP_BY_ID={"2100":55*1024*1024,"2154":6*1024*1024,"2157":16*1024*1024,"18326":20*1024*1024,"18422":45*1024*1024}
MAX_STREAM_TOTAL=350*1024*1024
MAX_SELECTED_STREAM=80*1024*1024

def get(dataset):
    data=[];size=0;digest=sha256()
    source=f'https://data.bus-data.dft.gov.uk/timetable/dataset/{dataset}/download/'
    with urlopen(Request(source,headers={"User-Agent":"OpenRoad-PTv2-Bristol-Bounded-TXC/1.0"}),timeout=30) as r:
        p=urlsplit(r.geturl())
        if p.scheme!="https" or p.hostname!="data.bus-data.dft.gov.uk":raise ValueError("Unexpected download host")
        while True:
            buf=r.read(1024*1024)
            if not buf:break
            size+=len(buf)
            if size>MAX_ZIP_BY_ID[dataset]:raise ValueError("Operator ZIP exceeds approved compressed download limit")
            data.append(buf);digest.update(buf)
    return BytesIO(b"".join(data)),size,digest.hexdigest()

def inspect(zfile,size,digest,dataset):
    with ZipFile(zfile) as z:
        items=[x for x in z.infolist() if not x.is_dir()]
        total=sum(i.file_size for i in items)
        if len(items)>250:
            raise ValueError("Too many archive members")
        partial=total>MAX_STREAM_TOTAL
        selected=items
        if partial:
            selected=[x for x in items if re.search(
                r'(^|[^A-Za-z0-9])75([^A-Za-z0-9]|$)',
                PurePosixPath(x.filename).name,re.I)]
            selected=sorted(selected,key=lambda x:x.file_size)
            total_selected=0
            capped=[]
            for info in selected:
                if info.file_size>MAX_MEMBER or total_selected+info.file_size>MAX_SELECTED_STREAM:
                    continue
                capped.append(info)
                total_selected+=info.file_size
            selected=capped
        nocs=Counter();found=[];routes=0;trips=0
        for info in selected:
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
            "source":"Official BODS First Bus catalogue candidate",
            "dataset_id":dataset, "sha256":digest, "download_bytes":size,
            "xml_members_total":len(items),"xml_members_inspected":len(selected),"expanded_bytes_declared":total,
            "partial_filename_scoped_inspection":partial,
            "operator_codes":dict(nocs),"matching_line_75_files":found,
            "routes_observed":routes,"vehicle_journeys_observed":trips,
            "date_specific_departures_verified":False,
            "production_acceptance_cases_passed":0
        },sort_keys=True))
        return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--dataset",choices=sorted(MAX_ZIP_BY_ID),default="2154")
    args=p.parse_args()
    zipped,size,digest=get(args.dataset)
    raise SystemExit(inspect(zipped,size,digest,args.dataset))
