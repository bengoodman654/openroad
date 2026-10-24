#!/usr/bin/env python3
"""One-shot bounded inspection of public BODS TXC dataset 20442 on disposable runner.

Not a journey planner or production parser. No data sent to JustHostMe.
"""
from collections import Counter
from pathlib import PurePosixPath
from hashlib import sha256
from io import BytesIO
import json
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from zipfile import ZipFile,BadZipFile
from xml.etree import ElementTree

SOURCE="https://data.bus-data.dft.gov.uk/timetable/dataset/20442/download/"
MAX_ZIP=16*1024*1024
MAX_EXPANDED=180*1024*1024
MAX_XML=6*1024*1024
MAX_PARSE_TOTAL=36*1024*1024
MAX_PREFIX_PER_FILE=1024*1024
WANTED={"9","11","12X"}

def get():
    chunks=[];size=0;hash_obj=sha256()
    with urlopen(Request(SOURCE,headers={"User-Agent":"OpenRoad-PTv2-Bounded-Timetable-Research/1.0"}),timeout=30) as response:
        p=urlsplit(response.geturl())
        if p.scheme!="https" or p.hostname!="data.bus-data.dft.gov.uk":
            raise ValueError("Unexpected redirect host")
        while 1:
            data=response.read(1024*1024)
            if not data:break
            size+=len(data)
            if size>MAX_ZIP:raise ValueError("Download exceeds 16 MiB cap")
            chunks.append(data)
            hash_obj.update(data)
    return BytesIO(b"".join(chunks)),size,hash_obj.hexdigest()

def text_items(root,local_name):
    found=[]
    for elem in root.iter():
        if elem.tag.rsplit("}",1)[-1]==local_name:
            v=(elem.text or "").strip()
            if v:found.append(v)
    return found

def prefix_labels(raw):
    """Bounded XML prefix metadata discovery. No complete XML file required."""
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        return set(),set()
    parser=ElementTree.XMLPullParser(events=["end"])
    parser.feed(raw)
    lines=set();operators=set()
    for _,elem in parser.read_events():
        tag=elem.tag.rsplit("}",1)[-1]
        if tag in ("LineName","NationalOperatorCode"):
            val=(elem.text or "").strip()
            if val and len(val)<=24:
                if tag=="LineName":lines.add(val)
                else:operators.add(val)
        elem.clear()
    return lines,operators

def inspect(filelike,size,digest):
    with ZipFile(filelike) as z:
        infos=[f for f in z.infolist() if not f.is_dir()]
        if len(infos)>4000:raise ValueError("Too many archive members")
        total=sum(x.file_size for x in infos)
        over_full_import_limit=total>MAX_EXPANDED
        for info in infos:
            parts=PurePosixPath(info.filename).parts
            if info.filename.startswith("/") or ".." in parts or not parts:
                raise ValueError("Unsafe member path")
        extensions=Counter(PurePosixPath(f.filename).suffix.lower() or "(none)" for f in infos)
        print(json.dumps({
           "source":"BODS official dataset 20442", "retrieved_archive_bytes":size,
           "sha256":digest, "archive_members":len(infos),
           "expanded_bytes_declared":total, "full_import_exceeds_180MiB_gate":over_full_import_limit, "extensions":dict(extensions),
           "largest_members":[
             {"name":PurePosixPath(f.filename).name[:110],"bytes":f.file_size}
             for f in sorted(infos,key=lambda x:x.file_size,reverse=True)[:6]]
        },sort_keys=True))
        prefix_lines=Counter();prefix_ops=Counter();prefix_bytes=0;prefix_errors=0
        prefix_files={}
        for info in [x for x in infos if x.filename.lower().endswith(".xml")]:
            with z.open(info) as part:
                raw=part.read(MAX_PREFIX_PER_FILE)
            prefix_bytes+=len(raw)
            try:found,operators=prefix_labels(raw)
            except ElementTree.ParseError:
                prefix_errors+=1
                continue
            for name in found:prefix_lines[name]+=1
            for code in operators:prefix_ops[code]+=1
            for name in found.intersection(WANTED):
                prefix_files.setdefault(name,[]).append(PurePosixPath(info.filename).name[:110])
        print(json.dumps({
            "prefix_bytes_scanned":prefix_bytes,
            "prefix_xml_errors":prefix_errors,
            "prefix_target_lines":{k:prefix_lines.get(k,0) for k in sorted(WANTED)},
            "prefix_target_filenames":{k:v[:12] for k,v in prefix_files.items()},
            "prefix_noc_codes":prefix_ops.most_common(10),
            "note":"XML prefix discovery only; no stop/time/calendar validation"
        },sort_keys=True))
        scanned=0; parsed=0; used=0; skipped=0
        route_lines=Counter(); operator_codes=Counter(); roots=Counter(); errors=0
        xmls=[f for f in infos if f.filename.lower().endswith(".xml")]
        for info in xmls:
            if info.file_size>MAX_XML or used+info.file_size>MAX_PARSE_TOTAL:
                skipped+=1
                continue
            with z.open(info) as source:
                raw=source.read(MAX_XML+1)
            if len(raw)>MAX_XML or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                skipped+=1
                continue
            scanned+=1;used+=len(raw)
            try:root=ElementTree.fromstring(raw)
            except ElementTree.ParseError:
                errors+=1
                continue
            parsed+=1;roots[root.tag.rsplit("}",1)[-1]]+=1
            for n in text_items(root,"LineName"):
                if len(n)<=20:route_lines[n]+=1
            for n in text_items(root,"NationalOperatorCode"):
                if len(n)<=12:operator_codes[n]+=1
        print(json.dumps({
           "xml_members":len(xmls),"xml_parsed":parsed,"xml_parse_errors":errors,
           "xml_skipped_due_to_limits":skipped,"xml_bytes_examined":used,
           "xml_document_root_types":dict(roots),
           "target_line_appearances":{x:route_lines.get(x,0) for x in sorted(WANTED)},
           "operator_codes_in_sample":operator_codes.most_common(12),
           "matched_lines_are_candidates_only":True,
           "production_acceptance_cases_passed":0
        },sort_keys=True))
        if not infos:raise ValueError("Empty official archive")
def main():
    filelike,size,digest=get()
    inspect(filelike,size,digest)
if __name__=="__main__":main()
