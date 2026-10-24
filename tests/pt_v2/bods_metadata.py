"""Select candidate operator-scoped BODS datasets without making network requests.

A matching public line number is merely candidate evidence: it does not establish
authoritative trip times, operating dates, directions, or stop codes.
"""
from __future__ import annotations
from datetime import date
from urllib.parse import urlsplit
import ipaddress
import re

OPERATORS={
  "BRI-75":{"noc":"FBRI","operator":"First West of England","line":"75"},
  "COV-11":{"noc":"TCVW","operator":"National Express Coventry","line":"11"},
  "COV-12X":{"noc":"TCVW","operator":"National Express Coventry","line":"12X"},
  "COV-9":{"noc":"TCVW","operator":"National Express Coventry","line":"9"},
}
class MetadataError(ValueError): pass

def public_https_url(url):
    if not isinstance(url,str) or len(url)>2048:return False
    try:
        p=urlsplit(url)
        if p.scheme!="https" or not p.hostname or p.username or p.password or p.fragment:return False
        if p.query:return False  # prevent forwarding credential-bearing/signed query parameters
        h=p.hostname.strip(".").lower()
        if h in ("localhost",) or h.endswith((".local",".internal",".localhost")):return False
        try:
            ip=ipaddress.ip_address(h)
            if not ip.is_global:return False
        except ValueError:
            if "." not in h or not re.fullmatch(r"[a-z0-9.-]+",h):return False
        return True
    except (ValueError,TypeError):return False

def select(metadata,noc,line,service_date=None):
    if not isinstance(metadata,dict) or not isinstance(metadata.get("results"),list):
        raise MetadataError("Expected BODS dataset results array")
    if not re.fullmatch(r"[A-Z0-9]{2,8}",noc):raise MetadataError("Invalid operator NOC")
    if not re.fullmatch(r"[A-Za-z0-9]{1,10}",line):raise MetadataError("Invalid route code")
    if not isinstance(service_date,(date,type(None))):raise MetadataError("Date must be date or None")
    selected=[]
    for row in metadata["results"]:
        if not isinstance(row,dict):continue
        codes=row.get("noc",[])
        if isinstance(codes,str):codes=[codes]
        if not isinstance(codes,list) or noc not in [str(x).upper() for x in codes]:continue
        if row.get("status")!="published":continue
        lines=row.get("lines",[])
        if isinstance(lines,str):lines=[lines]
        if not isinstance(lines,list):lines=[]
        # If the dataset omits its line list we cannot reject it from metadata alone.
        known_lines=[str(x).strip().upper() for x in lines if str(x).strip()]
        line_match=line.upper() in known_lines if known_lines else None
        if line_match is False:continue
        if service_date:
            low=row.get("firstStartDate")
            high=row.get("lastEndDate")
            if isinstance(low,str) and len(low)>=10 and low[:10]>service_date.isoformat():continue
            if isinstance(high,str) and len(high)>=10 and high[:10]<service_date.isoformat():continue
        raw_url=row.get("url")
        selected.append({
            "dataset_id":row.get("id"),"name":str(row.get("name",""))[:140],
            "operator_name":str(row.get("operatorName",""))[:140],
            "noc":noc,"line":line,"line_metadata_match":line_match,
            "status":"published","modified":row.get("modified"),
            "last_end_date":row.get("lastEndDate"),
            "download_url":raw_url if public_https_url(raw_url) else None,
            "manual_url_review_required":not public_https_url(raw_url),
            "evidence":"BODS metadata candidate only; timetable archive not yet validated",
        })
    return selected

def verify_source_identity(expected_noc,expected_line,observed_nocs,observed_lines,geography_confirmed=False):
    """Source metadata alone is never enough for an ACCEPTED timetable fixture.

    Observations must be from the *same service-bearing XML members*, not from
    unrelated operators elsewhere in a multi-operator ZIP.
    """
    if not isinstance(observed_nocs,(list,tuple,set)) or not observed_nocs:
        return "NEEDS_XML_OPERATOR_EVIDENCE"
    if expected_noc not in set(observed_nocs):
        return "REJECT_WRONG_OPERATOR"
    if expected_line not in set(observed_lines):
        return "REJECT_WRONG_SERVICE"
    if not geography_confirmed:
        return "NEEDS_STOP_AND_GEOGRAPHY_EVIDENCE"
    return "CANDIDATE_NEEDS_CALENDAR_AND_TRIP_VALIDATION"
