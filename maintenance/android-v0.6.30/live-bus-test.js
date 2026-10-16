'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const js=fs.readFileSync(process.argv[2],'utf8');
const begin=js.indexOf('  function busLiveReference(data){');
const end=js.indexOf('  function renderBusServiceContent()',begin);
assert(begin>=0&&end>begin,'live reference helper exists');
function run(data, mapCenter, user){
 const context={
   map:{getCenter(){return mapCenter;}},
   current:user,
   haversineMeters(a,b,c,d){return Math.hypot(a-c,b-d);}
 };
 vm.createContext(context);
 vm.runInContext(js.slice(begin,end),context);
 const p=context.busLiveReference(data);
 return p&&[p.lat,p.lon];
}
const route={stops:[{lat:51.46,lon:-2.60},{lat:51.54,lon:-2.59},{lat:51.57,lon:-2.58}]};
assert.deepStrictEqual(run(route,{lat:51.541,lng:-2.591},{lat:51.46,lon:-2.6}),[51.54,-2.59],
 'map shows distant part of service: live feed uses route stop, not GPS');
assert.deepStrictEqual(run(route,{lat:51.569,lng:-2.580},{lat:51.46,lon:-2.6}),[51.57,-2.58],
 'panning the map moves the live feed search to the appropriate section');
assert.deepStrictEqual(run({geometries:[{coordinates:[[-2.6,51.46],[-2.5,51.5]]}]},
 {lat:51.501,lng:-2.502},{lat:51.46,lon:-2.6}),[51.5,-2.5],
 'a route without stops uses map geometry');
assert(js.includes('busServiceTargetStop=null;++busLiveRequestId;busServiceReturnSheet='),
 'general bus search clears stale boarding stop and pending live request');
assert(js.includes('busServiceTargetStop=Number.isFinite(tl)&&Number.isFinite(tn)?'),
 'journey leg sets the new boarding stop or null');
assert(js.includes('native().lookupBusRouteNear(clean,Number(focus.lat),Number(focus.lng),id)'),
 'bus-number lookup uses visible map area');
assert(js.includes('++busLiveRequestId;clearBusRouteMarkers();'),
 'new route invalidates stale responses');
assert(js.includes("String(data?.line||'').toLowerCase()!==String(busServiceData.line||'').toLowerCase()"),
 'responses from earlier routes are rejected');
console.log('OpenRoad v0.6.30: remote-route anchor, panning, geometry fallback, route-switch safety PASS');
