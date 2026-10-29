#!/usr/bin/env python3
"""Bounded review of CURRENT release source. Prints only named route routines."""
from pathlib import Path
import re
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/uk/co/bengoodman/clearroute"
targets={
  "TransitClient.java":["cancelRouteWork","routeWithStops","route",
                        "onProgress","routeWorkCancelled","budgeted",
                        "rail","live","bus"],
  "OpenRoadServerClient.java":["postSigned","route","status","configured",
                               "requirePaired"],
  "MainActivity.java":["cancelRouteRequests","routeRequests","onRoute"],
}
for file,words in targets.items():
    lines=(base/file).read_text().splitlines()
    print("FILE",file,"lines",len(lines))
    count=0
    for i,line in enumerate(lines):
        if re.search(r"^\s*(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?]+\s+\w+\s*\(",line):
            if any(re.search(r"\b"+re.escape(x)+r"\b",line) for x in words):
                print("JAVA_METHOD",i+1,re.sub(r"\s+"," ",line.strip())[:180])
                count+=1
        if count>60:break
js=(root/"app/src/main/assets/app.js").read_text().splitlines()
print("JS lines",len(js))
for word in ["openroadPtBackOneScreen","openroadPtXAction","setRoutePlanningActive",
             "onRouteLiveUpdate","cancelActiveRouteRequest","transitNavigation",
             "showTransitSearchFailure"]:
    at=[i for i,x in enumerate(js) if re.search(r"(?:function\s+|const\s+|let\s+)"+re.escape(word)+r"\b",x)]
    print("JS_IDENTIFIER",word,"lines",[i+1 for i in at[:3]])
for word in ["route","rail","live","routeWithStops","stop"]:
    at=[i for i,x in enumerate((base/"TransitClient.java").read_text().splitlines()) if word in x.lower()]
    print("JAVA_OCCURRENCES",word,"count",len(at))
