#!/usr/bin/env python3
"""Deterministic OpenRoad v0.6.30 live-bus UX patch. No network calls."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
asset=root/"app/src/main/assets/app.js"
s=asset.read_text(encoding="utf-8")

def one(before,after):
    global s
    count=s.count(before)
    if count!=1:
        raise SystemExit(f"Expected 1 occurrence, found {count}: {before[:85]}")
    s=s.replace(before,after,1)

old="  function geoDistanceSq(lat,lon,ref){if(!ref)return 0;const x=(lon-ref.lon)*Math.cos((lat+ref.lat)*Math.PI/360),y=lat-ref.lat;return x*x+y*y;}"
new=old+"""
  // Geographical tile for the selected service, never an unrelated previous route.
  // Prefer the section of the published route closest to the map viewport.
  function busLiveReference(data){
    const stops=Array.isArray(data?.stops)?data.stops:[];
    const points=stops.map(s=>({lat:Number(s.lat),lon:Number(s.lon)}))
      .filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon));
    if(!points.length){
      (Array.isArray(data?.geometries)?data.geometries:[]).forEach(g=>{
        (Array.isArray(g?.coordinates)?g.coordinates:[]).forEach(p=>{
          const lon=Number(p?.[0]),lat=Number(p?.[1]);
          if(Number.isFinite(lat)&&Number.isFinite(lon))points.push({lat,lon});
        });
      });
    }
    let focus=null;
    try{
      const c=map?.getCenter?.();
      if(c&&Number.isFinite(Number(c.lat))&&Number.isFinite(Number(c.lng)))
        focus={lat:Number(c.lat),lon:Number(c.lng)};
    }catch(_){}
    if(!focus&&current&&Number.isFinite(Number(current.lat))&&Number.isFinite(Number(current.lon)))
      focus={lat:Number(current.lat),lon:Number(current.lon)};
    if(!points.length)return focus;
    if(!focus)return points[0];
    return points.reduce((best,p)=>
      haversineMeters(p.lat,p.lon,focus.lat,focus.lon)<
      haversineMeters(best.lat,best.lon,focus.lat,focus.lon)?p:best,points[0]);
  }
"""
one(old,new)
one("else vehicles.sort((a,b)=>geoDistanceSq(Number(a.lat),Number(a.lon),current)-geoDistanceSq(Number(b.lat),Number(b.lon),current));",
    "else {const ref=busLiveReference(data);vehicles.sort((a,b)=>geoDistanceSq(Number(a.lat),Number(a.lon),ref)-geoDistanceSq(Number(b.lat),Number(b.lon),ref));}")
one("const ref=busServiceTargetStop||current||((data.stops||[])[0]?{lat:Number(data.stops[0].lat),lon:Number(data.stops[0].lon)}:null);",
    "const ref=busServiceTargetStop||busLiveReference(data);")
one("clearBusRouteMarkers();busServiceData=data||{};busServiceTab='timetable';",
    "++busLiveRequestId;clearBusRouteMarkers();busServiceData=data||{};busServiceTab='timetable';")
# In a general bus-number search, clear any stop retained from a previous route.
one("busServiceReturnSheet=el('routeCard')&&!el('routeCard').classList.contains('hidden')?'routeCard':'none';const id=++busRouteRequestId;",
    "busServiceTargetStop=null;++busLiveRequestId;busServiceReturnSheet=el('routeCard')&&!el('routeCard').classList.contains('hidden')?'routeCard':'none';const id=++busRouteRequestId;")
# Look up the service in the visible map area, not the device's GPS position.
one("native()?.lookupBusRoute?.(clean,id);",
    "const focus=map?.getCenter?.();if(focus&&Number.isFinite(Number(focus.lat))&&Number.isFinite(Number(focus.lng))&&native()?.lookupBusRouteNear)native().lookupBusRouteNear(clean,Number(focus.lat),Number(focus.lng),id);else native()?.lookupBusRoute?.(clean,id);")
# A new journey leg must always override a stop from a different bus service.
one("if(!busServiceTargetStop){const tl=Number(leg.fromLat),tn=Number(leg.fromLon);if(Number.isFinite(tl)&&Number.isFinite(tn))busServiceTargetStop={id:leg.fromAtco||leg.fromStopId||'',name:leg.from||'Boarding stop',lat:tl,lon:tn};}",
    "++busLiveRequestId;const tl=Number(leg.fromLat),tn=Number(leg.fromLon);busServiceTargetStop=Number.isFinite(tl)&&Number.isFinite(tn)?{id:leg.fromAtco||leg.fromStopId||'',name:leg.from||'Boarding stop',lat:tl,lon:tn}:null;")
# Avoid processing a late response for the previously selected service.
one("if(requestId!==busLiveRequestId)return;if(busServiceData){busServiceData.vehicles=",
    "if(requestId!==busLiveRequestId||!busServiceData||String(data?.line||'').toLowerCase()!==String(busServiceData.line||'').toLowerCase())return;if(busServiceData){busServiceData.vehicles=")
one("el('backBusServiceBtn').onclick=()=>{show('busServiceSheet',false);",
    "el('backBusServiceBtn').onclick=()=>{++busLiveRequestId;show('busServiceSheet',false);")
asset.write_text(s,encoding="utf-8")

def textpatch(path,before,after):
    p=root/path
    txt=p.read_text(encoding="utf-8")
    if before not in txt:raise SystemExit(f"Missing {before} in {path}")
    p.write_text(txt.replace(before,after),encoding="utf-8")

textpatch("app/build.gradle","versionCode 89","versionCode 90")
textpatch("app/build.gradle","0.6.29","0.6.30")
textpatch("app/src/main/assets/index.html","0.6.29","0.6.30")
textpatch("app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java","0.6.29","0.6.30")
textpatch("validate.sh","0.6.29","0.6.30")
textpatch("validate.sh","versionCode 89","versionCode 90")
print("Patched OpenRoad v0.6.30: map-centred service lookup, fresh route context, live-bus reference selection")
