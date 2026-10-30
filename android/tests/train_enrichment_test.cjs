'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const ui=read('app/src/main/assets/app.js');
const styles=read('app/src/main/assets/styles.css');
const bridge=read('app/src/main/java/uk/co/bengoodman/clearroute/MainActivity.java');
const client=read('app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java');
const timetables=['requestSelectedTrainDetails','requestSelectedTrainLive','trainDetailsCache',
  'onTrainTimetableLoaded','onTrainLiveLoaded','showTrainTimetableList',
  'Timetable','Hide timetable','rail-inline-spinner','live.platform','railGeometryNote'];
for(const name of timetables)assert.ok(ui.includes(name),'Missing staged rail UI '+name);
assert.ok(styles.includes('max-height: min(50dvh, 50vh) !important'),'Journey panel must remain half height');
assert.ok(styles.includes('rail-inline-spinner'),'Show enrichment activity');
assert.ok(ui.includes('drawRoutes(navigating,false)'),'Enrichment must not reset map camera');
assert.ok(ui.includes("onRoute(data, requestedIndex=0, restored=false"),'Initial result must be independent');
assert.ok(ui.includes('requestSelectedTrainDetails(selectedRoute)'),'Request late enrichment after results');
assert.ok(ui.includes('if(requestId && requestId!==routeRequestId)'), 'Discard stale journey responses');
for(const code of ['requestTrainTimetable','requestTrainLive']){
  assert.ok(bridge.includes('@JavascriptInterface public void '+code),'Bridge not asynchronous '+code);
  assert.ok(client.includes('JSONObject '+(code==='requestTrainLive'?'trainLive':'trainTimetable')+'('),'Missing signed backend request');
}
assert.ok(ui.includes('new Map(),trainLiveCache=new Map()'),'Cache rail requests to prevent duplicate loads');
assert.ok(ui.includes('if(force && Date.now()-(lastTrainLiveFetch.get(key)||0)<120000)'),
  'Respect Rail Data throttle when refreshing');
console.log('TRAIN_ENRICHMENT_UI_ASYNC_TESTS_OK');
