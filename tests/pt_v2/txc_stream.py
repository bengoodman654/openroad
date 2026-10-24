"""Bounded single-pass TransXChange metadata scanner; no DOM or full XML buffering."""
from collections import Counter
from xml.parsers import expat

MAX_MEMBER=40*1024*1024
TARGET_FIELDS={"LineName","NationalOperatorCode","ServiceCode","OperatorShortName"}
class TXCStreamError(ValueError): pass

def scan(stream, limit=MAX_MEMBER):
    if not 1<=limit<=MAX_MEMBER:raise TXCStreamError("Unbounded stream limit")
    parser=expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    def block_dtd(*_):raise TXCStreamError("DTD not permitted")
    parser.StartDoctypeDeclHandler=block_dtd
    parser.ExternalEntityRefHandler=lambda *_:0
    seen={k:set() for k in TARGET_FIELDS}
    counts=Counter()
    active=None;buf=[];buflen=0
    def start(name,_attrs):
        nonlocal active,buf,buflen
        tag=name.rsplit("}",1)[-1].rsplit(":",1)[-1]
        if tag in TARGET_FIELDS:
            active=tag;buf=[];buflen=0
        if tag in ("VehicleJourney","Route","JourneyPattern","StopPointRef"):
            counts[tag]+=1
    def char(data):
        nonlocal buflen
        if active and buflen<200:
            buf.append(data[:200-buflen]);buflen+=len(buf[-1])
    def end(name):
        nonlocal active,buf,buflen
        tag=name.rsplit("}",1)[-1].rsplit(":",1)[-1]
        if active==tag:
            value="".join(buf).strip()
            if 0<len(value)<=160:seen[tag].add(value)
            active=None;buf=[];buflen=0
    parser.StartElementHandler=start
    parser.CharacterDataHandler=char
    parser.EndElementHandler=end
    amount=0
    while True:
        chunk=stream.read(65536)
        if not chunk:break
        amount+=len(chunk)
        if amount>limit:raise TXCStreamError("Member streaming budget exceeded")
        parser.Parse(chunk,False)
    parser.Parse(b"",True)
    return {"bytes":amount,"lines":sorted(seen["LineName"]),"nocs":sorted(seen["NationalOperatorCode"]),
            "service_codes":len(seen["ServiceCode"]),"counts":dict(counts)}
