"""Read bounded source excerpts from committed ZIP archives on GitHub Actions.

No secrets, upstream HTTP, branch merge, deployment or app build involved.
"""
from __future__ import annotations
import re
from zipfile import ZipFile

ARCHIVES = {
 "android": "OpenRoad-v0.6.31-source.zip",
 "php": "OpenRoad-Transport-Server-v0.2.5-source.zip"
}
PATTERNS = {
 "app.js": [
  "function cancelActiveRouteRequest","function calculateRoute",
  "function acceptSearchResult","function armTransitSearchWatchdog",
  "function finishRouteCalculationUi","function startTransitNavigation",
  "function stopTransitNavigation",
  "Where to","whereTo","routeRequest","routeGeneration",
 ],
 "TransitClient.java": [
  "beginRouteWork","cancelRouteWork","routeWorkCancelled",
  "completeSearch","routeWithStops","routeOnce","Future","Executor",
 ],
 "journeys.php": ["<?php", "function","openroad_plan_bus","$_","token","cancel"],
 "router.php": ["function openroad_plan_bus","or_route_check_budget",
               "or_route_deadline","function or_make_journey"],
}

def main():
    budget = 60000
    for area, archive in ARCHIVES.items():
        with ZipFile(archive) as z:
            names = [n for n in z.namelist() if
                     n.endswith(("/app.js","/TransitClient.java",
                                 "/journeys.php","/router.php"))]
            for name in names:
                text=z.read(name).decode("utf-8",errors="replace")
                lines=text.splitlines()
                target=name.rsplit("/",1)[-1]
                hits=[]
                for i,line in enumerate(lines):
                    if any(term.lower() in line.lower()
                           for term in PATTERNS[target]):
                        hits.append(i)
                # Aim for compact, relevant code previews. Deduplicate contexts.
                window = 13 if target in ("app.js","TransitClient.java") else 20
                blocks=[]
                for hit in hits:
                    lo=max(0,hit-5)
                    hi=min(len(lines),hit+window)
                    if blocks and lo<=blocks[-1][1]:
                        blocks[-1]=(blocks[-1][0],max(hi,blocks[-1][1]))
                    else:
                        blocks.append((lo,hi))
                print("FILE",name,"LINES",len(lines),"HITS",len(hits),flush=True)
                used=0
                for lo,hi in blocks:
                    section="\n".join(
                        f"{j+1:05d} {lines[j]}" for j in range(lo,hi))
                    section=re.sub(
                        r'(?i)(key|secret|token|password)(\s*[=:]\s*)(["\\x27])[^"\\x27]+\\3',
                        r'\1\2"REDACTED"',section)
                    if used+len(section)>budget:
                        print("TRUNCATED",used,flush=True);break
                    print(f"EXCERPT {lo+1}-{hi}\n{section}",flush=True)
                    used+=len(section)
                print("FILE_DONE",name,"BYTES",used,flush=True)

if __name__=="__main__":
    main()
