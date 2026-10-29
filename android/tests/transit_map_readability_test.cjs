'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..'),asset=path.join(root,'app/src/main/assets');
const js=fs.readFileSync(path.join(asset,'app.js'),'utf8');
const html=fs.readFileSync(path.join(asset,'index.html'),'utf8');
const css=fs.readFileSync(path.join(asset,'styles.css'),'utf8');
const start=js.indexOf('  const BUS_LEG_COLOURS='),end=js.indexOf('  function addStopDirectionIcon()',start);
assert(start>=0&&end>start,'Service colour and direction helpers present');
const ctx={normaliseTransitMode:m=>m,transitModeColour:m=>m==='foot'?'#888888':'#aaaaaa',
  bearingTo:(a,b,c,d)=>(Math.atan2(d-b,c-a)*180/Math.PI+360)%360};
vm.createContext(ctx);vm.runInContext(js.slice(start,end),ctx);
const route={transitLegs:[{mode:'foot'}, {mode:'bus',line:'1'}, {mode:'foot'},
  {mode:'bus',line:'2'}, {mode:'bus',line:'3'}]};
const one=ctx.transitLegColour(route,1),two=ctx.transitLegColour(route,3),three=ctx.transitLegColour(route,4);
assert.equal(new Set([one,two,three]).size,3,'Three separate buses have different colours');
assert.equal(ctx.transitLegColour(route,1),one,'Colour stable on repeated render');
assert.equal(ctx.transitLegColour(route,1,false),'#aaaaaa','Unselected alternatives remain muted');
assert.equal(ctx.transitLegColour(route,0),'#888888','Walking leg is unaffected');
const stops=[{lat:51,lon:-2},{lat:51.01,lon:-2},{lat:51.01,lon:-1.99}];
assert.equal(ctx.stopTravelBearing(stops,0),0,'First stop arrow points along first segment');
assert.equal(ctx.stopTravelBearing(stops,1),90,'Middle stop arrow points along next segment');
assert.equal(ctx.stopTravelBearing(stops,2),90,'Last stop arrow inherits arrival direction');
assert.equal(ctx.stopTravelBearing([stops[0]],0),null,'Unknown direction is not fabricated');
const layers=[],sources={};ctx.routeLayerIds=[];ctx.transitStopData=new Map();ctx.navigating=false;
ctx.map={addSource(id,data){sources[id]=data;},addLayer(layer){layers.push(layer);}};
ctx.addStopDirectionIcon=()=> 'test-arrow';
const layerStart=js.indexOf('  function renderTransitStopLayer(route){');
const layerEnd=js.indexOf('  function renderBusStopSheet(',layerStart);
assert(layerStart>0&&layerEnd>layerStart);
vm.runInContext(js.slice(layerStart,layerEnd),ctx);
const withStops={transitLegs:[{mode:'bus',line:'1',stops},
  {mode:'foot'}, {mode:'bus',line:'2',stops:stops.map(s=>({lat:s.lat+.05,lon:s.lon+.05}))}]};
ctx.renderTransitStopLayer(withStops);
const features=sources['route-src-transit-stops'].data.features;
assert.equal(features.length,6,'Stops from both bus legs are rendered');
assert.notEqual(features[0].properties.stopColor,features[3].properties.stopColor,
  'Map stop colours distinguish the connecting bus');
assert.equal(features[0].properties.bearing,0,'Map source preserves vehicle direction');
const symbol=layers.find(x=>x.id==='route-transit-stop-direction');
assert(symbol&&symbol.type==='symbol'&&symbol.layout['icon-image']==='test-arrow',
  'Directional stop icons are drawn above the stop dots');
assert.match(js,/icon-rotate':\['get','bearing'\]/,'Stop arrows rotate with geographical bearing');
assert.match(js,/bearing-90/,'Vehicle arrow uses clockwise bearing from north');
for(const [sheet,back,close] of [
  ['transitDetailSheet','backTransitDetailBtn','closeTransitDetailBtn'],
  ['busServiceSheet','backBusServiceBtn','closeBusServiceBtn'],
  ['busStopSheet','backBusStopBtn','closeBusStopBtn']]){
  const content=html.split(`id="${sheet}"`)[1].split('</div>\n  </div>')[0];
  const nav=content.split('class="pt-sheet-navigation"')[1].split('</div>')[0];
  assert(nav.indexOf(`id="${back}"`)<nav.indexOf(`id="${close}"`),sheet+' Back left and X right');
}
assert.match(css,/route-sheet:not\(\.minimised\)>\.sheet-handle\{top:0;height:19px/,
  'Minimise gesture target separated from mode controls');
console.log('Transit map: distinct bus colours, directional stops/vehicles, top controls and grip passed');
