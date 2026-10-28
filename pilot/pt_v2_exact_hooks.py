"""Off-host bounded read-only extraction of exact integration hook call sites."""
from zipfile import ZipFile
import re
candidates={
 "OpenRoad-v0.6.31-source.zip": {
   "/app/src/main/assets/app.js":["routeSearchClearBtn", "routeRequestId", "cancelActiveRouteRequest", "function stopTransitNavigation", "onRouteLiveUpdate", "onRoute(data"],
   "/app/src/main/assets/index.html":["routeSearchClearBtn","searchInput","backBtn","stopNav"],
   "/app/src/main/java/uk/co/bengoodman/clearroute/MainActivity.java":["cancelRouteRequests","calculateTransitRouteWithStops", "onRoute("],
   "/app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java":["cancel","journeys.php", "openroad","post","route("],
 },
 "OpenRoad-Transport-Server-v0.2.5-source.zip":{
   "/private/lib/auth.php":["function openroad_require_signed", "device_id", "deviceId", "verify", "public_key", "signature", "fingerprint"],
 "/public/api/v1/journeys.php":["openroad_require_signed", "openroad_plan_bus"]
 }
}
for archive,names in candidates.items():
  with ZipFile(archive) as z:
    for suffix,terms in names.items():
      names_matching=[n for n in z.namelist() if n.endswith(suffix)]
      if len(names_matching)!=1:
        print("MISSING_OR_AMBIGUOUS",suffix,len(names_matching));continue
      path=names_matching[0]
      lines=z.read(path).decode("utf-8",errors="replace").splitlines()
      matches=[i for i,s in enumerate(lines) if any(term in s for term in terms)]
      print("FILE",path,"LINES",len(lines),"HITS",len(matches))
      printed=set()
      for i in matches[:24]:
        lo=max(0,i-4);hi=min(len(lines),i+7)
        for k in range(lo,hi):
          if k in printed:continue
          printed.add(k)
          s=lines[k]
          if len(s)>400:s=s[:400]+"... [TRUNCATED]"
          s=re.sub(r'(?i)(key|secret|password)(["\\x27]?\s*[:=]\s*)(["\\x27])[^"\\x27]+\\3',r'\1\2"REDACTED"',s)
          print(f"{k+1:05d} {s}")
