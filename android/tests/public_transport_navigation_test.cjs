'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'app/src/main/assets/index.html'),'utf8');
const js=fs.readFileSync(path.join(root,'app/src/main/assets/app.js'),'utf8');

for(const id of ['ptBackBtn','routeSearchClearBtn','backTransitPreferencesBtn',
  'closeTransitPreferencesBtn','backTransitDetailBtn','closeTransitDetailBtn',
  'backBusServiceBtn','closeBusServiceBtn','backBusStopBtn','closeBusStopBtn']){
  assert.match(html,new RegExp('id="'+id+'"'),'Navigation control exists: '+id);
  assert.match(js,new RegExp("el\\('"+id+"'\\)"),'Control is wired: '+id);
}
// The extracted handlers deliberately use stand-in sheets: no Android device,
// MapLibre, transport provider or network request is needed to check history.
const start=js.indexOf('  function backFromTransitDetail(){');
const end=js.indexOf("  el('backTransitDetailBtn').onclick=",start);
assert(start>0&&end>start,'Navigation handlers are present');
const visible=new Set(['busServiceSheet']);
const events=[];
const context={
  busLiveRequestId:4,busRouteRequestId:8,busStopRequestId:12,
  expandedTrainTimetable:'',selectedRoute:0,
  showTransitDetail(){events.push(['showTransitDetail']);},
  busServiceReturnSheet:'busStopSheet',busStopReturnSheet:'transitDetailSheet',
  busServiceTargetStop:{id:'stop-id'},routeResponse:{routes:[{}]},transitNavigation:null,
  show(id,on=true){events.push([id,on]);if(on)visible.add(id);else visible.delete(id);},
  clearBusRouteMarkers(){events.push(['clearBusRouteMarkers']);},
  closeRoutePlanner(){events.push(['closeRoutePlanner']);},
  drawRoutes(){events.push(['drawRoutes']);}
};
vm.createContext(context);
vm.runInContext(js.slice(start,end),context);
context.backFromBusService();
assert(!visible.has('busServiceSheet'),'Back closes bus route');
assert(visible.has('busStopSheet'),'Back restores the bus stop that opened the route');
assert.equal(context.busRouteRequestId,9,'Back invalidates late route responses');
assert.equal(context.busLiveRequestId,5,'Back invalidates late live-bus responses');
context.backFromBusStop();
assert(visible.has('transitDetailSheet'),'Back restores journey detail after a stop');
assert.equal(context.busStopRequestId,13,'Back invalidates late stop responses');
context.closeTransitSheet('transitDetailSheet');
assert(!visible.has('transitDetailSheet'),'X closes detail');
assert(visible.has('routeCard'),'X returns to route overview');
assert(events.some(x=>x[0]==='drawRoutes'),'Underlying route map is restored');
context.backFromTransitDetail();
assert(visible.has('routeCard'),'Detail Back returns to journey results');
assert.match(js,/routePlanningActive&&!transitNavigation[\s\S]{0,70}clearRouteBtn/,
  'Main Back returns to the destination without ending active navigation');
console.log('Public transport Back/X: nested bus, stop, detail, cancellation and overview passed');
