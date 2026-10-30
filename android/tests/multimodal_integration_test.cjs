'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=path.resolve(__dirname,'..');
const file=p=>fs.readFileSync(path.join(base,p),'utf8');
const client=file('app/src/main/java/uk/co/bengoodman/clearroute/OpenRoadServerClient.java');
const routing=file('app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java');
const js=file('app/src/main/assets/app.js');
const html=file('app/src/main/assets/index.html');
const match=(text,token)=>assert.ok(text.includes(token),'Missing '+token);
[
  'JSONObject multimodalJourneys(Context context','"/api/v1/multimodal.php"',
  'postSigned(context,root+"/api/v1/multimodal.php"','routes.length()==0',
  'route.optBoolean("clearRouteMultimodal",false)',
  'legs.length()!=geometry.length()',
  'lastMixedAt','now-lastMixedAt<45000'
].forEach(x=>match(client,x));
[
  'busEnabled && railEnabled','OpenRoadServerClient.multimodalJourneys',
  'return verifiedMixed','provider=multimodal outcome=unavailable',
  'OpenRoadServerClient.railJourneys','BodsJourneyPlanner.plan',
  'insideGreaterLondon(originLat, originLon)'
].forEach(x=>match(routing,x));
['showTransitDetail','transitLegColour','train','bus','onRailDepartures'].forEach(x=>match(js,x));
['backTransitDetailBtn','closeTransitDetailBtn','backBusServiceBtn',
 'closeBusServiceBtn','backBusStopBtn','closeBusStopBtn'].forEach(x=>match(html,'id="'+x+'"'));
console.log('MULTIMODAL_ANDROID_SOURCE_CHECKS_OK');
