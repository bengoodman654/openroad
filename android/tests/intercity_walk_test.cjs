'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(root,'app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java'),'utf8');
const ui=fs.readFileSync(path.join(root,'app/src/main/assets/app.js'),'utf8');
for(const key of ['requestSegmentedWalkingRoute','mergeVerifiedWalkingParts','requestActiveTravelRouteInternal',
  'distanceMetres(originLat,originLon,destLat,destLon)>80000.0',
  'requestActiveTravelRouteInternal(startLat,startLon,null,null,endLat,endLon,',
  '"cycle",0,avoidAreas','"walk",0,avoidAreas',
  'routePoints(seedRoute)','leg.optJSONArray("points")',
  'distanceMetres(points.get(0)[0]','Disconnected section',
  'Math.ceil(length/38000.0)','if(count>9)',
  'Thread.currentThread().isInterrupted()','previousTotalPoints',
  'clearRouteWalkSegments','routeOffsetInMeters']){
  assert.ok(src.includes(key),'Missing verified pedestrian intercity fallback: '+key);
}
assert.ok(src.includes('"pedestrian"')&&src.includes('Valhalla / OpenStreetMap pedestrian segments'));
assert.ok(ui.includes('if(previousMode!==mode&&!navigating)'), 'Mode switch should clear prior map route');
assert.ok(ui.includes("if(el('routeOptions'))el('routeOptions').textContent=''"), 'Clear stale loading message');
assert.ok(ui.includes('if(!routeResponse?.routes?.length){'),'Failed search disables navigation');
assert.ok(ui.includes("el('startNavBtn').disabled=true"),'Do not start a missing route');
console.log('INTERCITY_WALK_AND_STALE_MODE_REGRESSIONS_OK');
