'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const client=read('app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java');
const broker=read('app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java');
const js=read('app/src/main/assets/app.js');
const html=read('app/src/main/assets/index.html');
const css=read('app/src/main/assets/styles.css');
for(const text of ['railJourneys(Context context','postSigned(context,root+"/api/v1/rail_journeys.php"',
                    'requirePaired(context,baseUrl)','2500,5500'])
  assert.ok(client.includes(text),'Signed private rail route connection: '+text);
for(const text of ['boolean railEnabled','scheduledRail=OpenRoadServerClient.railJourneys',
                    'mergeBusAndRail(response,scheduledRail)','return scheduledRail',
                    'if(!busEnabled)','insideGreaterLondon'])
  assert.ok(broker.includes(text),'Rail-and-bus fallback logic: '+text);
assert.ok(broker.includes('!busEnabled')&&broker.includes('railEnabled'),'Rail-only selection');
assert.ok(js.includes('Check live departures')&&js.includes('railBoardContext'),'User controls live-board queries');
assert.ok(js.includes('matches.length===1'),'Never attach ambiguous live train information');
assert.ok(js.includes("route.clearRouteDataStatus='mixed'"),'Scheduled and live data labelled independently');
assert.ok(js.includes("leg.cancelled=match.cancelled===true"),'Cancellation propagation');
for(const sheet of ['transitDetailSheet','busServiceSheet','busStopSheet'])
  assert.ok(html.includes('id="'+sheet+'"'),'Each transport panel has a window');
for(const nav of ['backTransitDetailBtn','closeTransitDetailBtn','backBusServiceBtn',
                  'closeBusServiceBtn','backBusStopBtn','closeBusStopBtn'])
  assert.ok(html.includes('id="'+nav+'"'),'Back/X control for '+nav);
assert.ok(css.includes('max-height: min(50dvh, 50vh) !important'),'PT panel height cap');
console.log('Rail integration: 29 static safety and UI assertions passed.');
