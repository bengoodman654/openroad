#!/usr/bin/env python3
"""OpenRoad v0.6.32 normal-release UI-only patch from v0.6.31."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
def edit(path, before, after):
    p=root/path
    s=p.read_text(encoding="utf-8")
    if s.count(before)!=1:
        raise SystemExit("Changed source anchor: "+path+": "+str(s.count(before)))
    p.write_text(s.replace(before,after,1),encoding="utf-8")
js="app/src/main/assets/app.js"
html="app/src/main/assets/index.html"
edit(html,
 '      <button id="menuBtn" class="icon-btn" aria-label="Settings" title="Settings">',
 '      <button id="ptBackBtn" class="icon-btn hidden" type="button" aria-label="Back one public transport screen" title="Back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>\n'
 '      <button id="menuBtn" class="icon-btn" aria-label="Settings" title="Settings">')
edit(js,
 "    show('routeSearchClearBtn',routePlanningActive);show('starBtn',!routePlanningActive);",
 "    const ptFlow = mode==='transit' && (routePlanningActive||!!transitNavigation);\n"
 "    show('ptBackBtn',ptFlow);show('menuBtn',!ptFlow);\n"
 "    show('routeSearchClearBtn',routePlanningActive||ptFlow);\n"
 "    show('starBtn',!routePlanningActive&&!ptFlow);")
handlers="""
  function openroadPtBackOneScreen(){
    if(routePointSelectionActive()){
      resetRoutePointSelection();hideSearchDropdown();renderRoutePlanner();return;
    }
    for(const sheet of ['transitDetailSheet','busStopSheet','busServiceSheet']){
      if(!el(sheet)?.classList.contains('hidden')){show(sheet,false);return;}
    }
    if(routePlannerIsOpen()){closeRoutePlanner();return;}
    if(mode==='transit' && transitSearchRequest &&
       transitSearchRequest===routeRequestId){
      cancelActiveRouteRequest();toast('Search cancelled.');return;
    }
    // At the root Back does not terminate guidance.
  }
  function openroadPtXAction(){
    if(mode==='transit' && transitSearchRequest &&
       transitSearchRequest===routeRequestId){
      cancelActiveRouteRequest();
      if(!navigating && !routeResponse)
        showTransitSearchFailure('Search cancelled. No journey was changed.');
      return;
    }
    if(mode==='transit' && transitNavigation){
      if(window.confirm('Stop public transport navigation?'))
        stopTransitNavigation();
      return;
    }
    clearDestination();
  }
  el('ptBackBtn').onclick=e=>{e.stopPropagation();openroadPtBackOneScreen();};
"""
edit(js,
 "  el('routeSearchClearBtn').onclick=e=>{e.stopPropagation();clearDestination();};",
 handlers+"  el('routeSearchClearBtn').onclick=e=>{e.stopPropagation();openroadPtXAction();};")
edit(js,
 "      const previousId=selectedRouteId||routeResponse?.routes?.[selectedRoute]?.clearRouteId||'';routeResponse=data;",
 "      const previousId=selectedRouteId||routeResponse?.routes?.[selectedRoute]?.clearRouteId||'';\n"
 "      // Never silently switch journeys when late data arrives.\n"
 "      if(previousId&&!data.routes.some(r=>r?.clearRouteId===previousId))return;\n"
 "      routeResponse=data;")
edit("app/build.gradle","versionCode 91","versionCode 92")
edit("validate.sh","versionCode 91","versionCode 92")
for rel in ("app/build.gradle",html,
 "app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java","validate.sh"):
    p=root/rel
    text=p.read_text(encoding="utf-8")
    if "0.6.31" not in text:raise SystemExit("Wrong baseline version "+rel)
    p.write_text(text.replace("0.6.31","0.6.32"),encoding="utf-8")
for rel in ("app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java",
 "app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java"):
    if "ptV2Issue(" in (root/rel).read_text(encoding="utf-8"):
        raise SystemExit("Experimental research adapter must not go into normal release")
print("Patched release source v0.6.32, without experimental v2 routing")
