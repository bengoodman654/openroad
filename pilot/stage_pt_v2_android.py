"""Stage audited Android v0.6.31 PT UI fixes in a separate research ZIP."""
from __future__ import annotations
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from pilot.pt_v2_android_java_patch import patch_server,patch_transit

def replace_one(s, old, new):
    if s.count(old) != 1:
        raise ValueError("Source version/anchor changed: expected exactly one match")
    return s.replace(old, new, 1)

def stage(source, destination):
    with ZipFile(source) as z:
        names = z.namelist()
        def locate(suffix):
            match = [n for n in names if n.endswith("/" + suffix)]
            if len(match) != 1:
                raise ValueError("Ambiguous Android source file: " + suffix)
            return match[0]
        js_path = locate("app/src/main/assets/app.js")
        html_path = locate("app/src/main/assets/index.html")
        java_client_path = locate("app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java")
        java_transit_path = locate("app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java")
        js = z.read(js_path).decode("utf-8")
        html = z.read(html_path).decode("utf-8")
        html = replace_one(
            html,
            '      <button id="menuBtn" class="icon-btn" aria-label="Settings" title="Settings">',
            '      <button id="ptBackBtn" class="icon-btn hidden" type="button" aria-label="Back one public transport screen" title="Back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>\n'
            '      <button id="menuBtn" class="icon-btn" aria-label="Settings" title="Settings">')
        js = replace_one(
            js,
            "    show('routeSearchClearBtn',routePlanningActive);show('starBtn',!routePlanningActive);",
            "    const ptFlow = mode==='transit' && (routePlanningActive||!!transitNavigation);\n"
            "    show('ptBackBtn',ptFlow);show('menuBtn',!ptFlow);\n"
            "    show('routeSearchClearBtn',routePlanningActive||ptFlow);\n"
            "    show('starBtn',!routePlanningActive&&!ptFlow);")
        handlers = """
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
    // At root Back is a no-op: it must not stop guidance.
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
        js = replace_one(js,
            "  el('routeSearchClearBtn').onclick=e=>{e.stopPropagation();clearDestination();};",
            handlers +
            "  el('routeSearchClearBtn').onclick=e=>{e.stopPropagation();openroadPtXAction();};")
        js = replace_one(js,
            "      const previousId=selectedRouteId||routeResponse?.routes?.[selectedRoute]?.clearRouteId||'';routeResponse=data;",
            "      const previousId=selectedRouteId||routeResponse?.routes?.[selectedRoute]?.clearRouteId||'';\n"
            "      // An asynchronous update must not silently replace a chosen journey.\n"
            "      if(previousId&&!data.routes.some(r=>r?.clearRouteId===previousId))return;\n"
            "      routeResponse=data;")
        java_client = patch_server(z.read(java_client_path).decode("utf-8"))
        java_transit = patch_transit(z.read(java_transit_path).decode("utf-8"))
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=6) as out:
            for info in z.infolist():
                data = z.read(info.filename)
                if info.filename == js_path: data = js.encode("utf-8")
                elif info.filename == html_path: data = html.encode("utf-8")
                elif info.filename == java_client_path: data = java_client.encode("utf-8")
                elif info.filename == java_transit_path: data = java_transit.encode("utf-8")
                out.writestr(info, data)
    print("STAGED_RESEARCH_ONLY",destination)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--source",default="OpenRoad-v0.6.31-source.zip")
    a=p.parse_args()
    stage(a.source,a.output)

if __name__=="__main__": main()
