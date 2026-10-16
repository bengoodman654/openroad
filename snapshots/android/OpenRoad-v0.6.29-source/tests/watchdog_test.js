'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const js=fs.readFileSync(__dirname+'/../app/src/main/assets/app.js','utf8');
const begin=js.indexOf('  function stopTransitSearchWatchdog(){');
const end=js.indexOf('  function setDestination(',begin);
assert(begin>0&&end>begin,'UI watchdog snippet exists');
const calls=[],timers=[];
const box={classList:{add(){}},textContent:'',appendChild(){}};
const els={routeOptions:box,routeCard:{classList:{add(){}}},startNavBtn:{disabled:false}};
const context={
 transitSearchTimer:0,transitSearchRequest:0,routeRequestId:7,mode:'transit',routeResponse:null,pendingDirections:true,
 setTimeout(fn,ms){timers.push({fn,ms,stopped:false});return timers.length;},
 clearTimeout(i){if(timers[i-1])timers[i-1].stopped=true;},
 native(){return {cancelRouteRequests(id){calls.push(['cancel',id]);}}},
 el(id){return els[id]||null;},
 document:{createElement(tag){return {tagName:tag,className:'',textContent:'',append(){},onclick:null};}},
 show(name,val){calls.push(['show',name,val])},finishRouteCalculationUi(){calls.push(['finish'])},
 setRoutePlanningActive(){},toast(){},calculateRoute(){calls.push(['retry'])}
};
vm.createContext(context);vm.runInContext(js.slice(begin,end),context);
context.armTransitSearchWatchdog(7);
assert.strictEqual(timers[0].ms,19500);
timers[0].fn();
assert.strictEqual(context.routeRequestId,8,'timeout invalidates pending callbacks');
assert.deepStrictEqual(calls.find(x=>x[0]==='cancel'),['cancel',8]);
assert.strictEqual(els.startNavBtn.disabled,true,'cannot start missing route');
assert.strictEqual(timers[0].stopped,true);
context.armTransitSearchWatchdog(8);
context.routeRequestId=9;timers[1].fn();
assert.strictEqual(context.routeRequestId,9,'stale timeout did not invalidate newer search');
context.armTransitSearchWatchdog(9);
context.routeResponse={routes:[{}]};timers[2].fn();
assert.strictEqual(context.routeRequestId,10,'enrichment stopped after already viable route');
assert.strictEqual(calls.filter(x=>x[0]==='cancel').length,2);
console.log('UI watchdog: timeout, stale-search guard, successful-route preservation passed');
