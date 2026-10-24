#!/usr/bin/env python3
"""One-off HEAD-only probe of official BODS dataset 20442, run on a disposable GitHub runner."""
import argparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
import json

ALLOWED_DATASETS=("20442","2100","2154","2157","18326","18422")
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

def allowed(url):
    p=urlsplit(url)
    host=(p.hostname or "").lower()
    if p.scheme!="https" or p.username or p.password:return False
    return host=="data.bus-data.dft.gov.uk" or host in ("storage.googleapis.com",) or host.endswith((".amazonaws.com",".cloudfront.net",".digitaloceanspaces.com"))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset",choices=ALLOWED_DATASETS,default="20442")
    args=ap.parse_args()
    op=build_opener(NoRedirect())
    url=f"https://data.bus-data.dft.gov.uk/timetable/dataset/{args.dataset}/download/"
    for i in range(4):
        if not allowed(url):
            print("STOP: redirect host is outside reviewed provider/CDN hosts.")
            return 3
        req=Request(url,method="HEAD",headers={"User-Agent":"OpenRoad-PTv2-Source-Size-Check/1.0"})
        try: res=op.open(req,timeout=12)
        except HTTPError as e:res=e
        with res:
            status=res.status
            h=res.headers
            content_length=h.get("Content-Length")
            content_type=h.get("Content-Type","")
            print(json.dumps({"hop":i,"host":urlsplit(url).hostname,
              "http_status":status,"content_length":content_length,
              "content_type":content_type[:90]}))
            if status in (301,302,303,307,308):
                raw=h.get("Location")
                if not raw:
                    print("STOP: redirect without location")
                    return 4
                url=urljoin(url,raw)
                continue
            return 0 if status==200 else 5
    print("STOP: redirect chain too long")
    return 6
if __name__=="__main__":
    raise SystemExit(main())
