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

# Only previously inspected navigation functions; no keys, manifests or config.
safe_windows={
  "TransitClient.java":[(75,140),(202,330)],
  "OpenRoadServerClient.java":[(67,104),(139,189)],
}
for filename,spans in safe_windows.items():
    lines=(base/filename).read_text().splitlines()
    for a,b in spans:
        print("SOURCE_WINDOW",filename,a,b)
        for i in range(a-1,min(b,len(lines))):
            line=lines[i]
            # Do not print any unexpected hardcoded tokens or credentials.
            if re.search(r"(?:secret|api[_-]?key|private[_-]?key|password)",line,re.I):
                print(f"{i+1}: [REDACTED-SENSITIVE-LINE]")
            else:
                print(f"{i+1}: {line[:220]}")
for a,b in [(194,220),(1190,1260),(2080,2133)]:
    print("SOURCE_WINDOW app.js",a,b)
    for i in range(a-1,min(b,len(js))):
        print(f"{i+1}: {js[i][:220]}")
