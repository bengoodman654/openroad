'use strict';
/* Exercise the REAL functions inserted in the staged v0.6.31 app.js.
 * These are isolated function-level tests, not Android device/UI tests. */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const app = fs.readFileSync(process.argv[2], 'utf8');
const start = app.indexOf('  function openroadPtBackOneScreen(){');
const end = app.indexOf("  el('ptBackBtn').onclick", start);
assert(start >= 0 && end > start, 'Exact staged handlers not found');
const source = app.slice(start, end);
let passed = 0;
function make(overrides = {}) {
  const calls = [];
  const settings = {
    mode: 'transit',
    transitSearchRequest: 7,
    routeRequestId: 7,
    navigating: false,
    routeResponse: null,
    transitNavigation: null,
    routePointSelectionActive: () => false,
    resetRoutePointSelection: () => calls.push('reset-point'),
    hideSearchDropdown: () => calls.push('hide-dropdown'),
    renderRoutePlanner: () => calls.push('render-planner'),
    el: id => ({classList: {contains: () => true}}),
    show: (name, value) => calls.push('show:' + name + ':' + value),
    routePlannerIsOpen: () => false,
    closeRoutePlanner: () => calls.push('close-planner'),
    cancelActiveRouteRequest: () => calls.push('cancel-search'),
    toast: text => calls.push('toast:' + text),
    showTransitSearchFailure: text => calls.push('failure:' + text),
    window: {confirm: () => false},
    stopTransitNavigation: () => calls.push('stop-guidance'),
    clearDestination: () => calls.push('clear-destination'),
    ...overrides
  };
  const names = Object.keys(settings);
  const f = new Function(...names,
    source + '\nreturn {openroadPtBackOneScreen,openroadPtXAction};');
  const funcs = f(...names.map(k => settings[k]));
  return {...funcs, calls};
}
function check(label, fn) {
  fn();
  passed++;
  console.log('PASS', label);
}

check('X cancels a running transit lookup without clearing destination', () => {
  const t = make();
  t.openroadPtXAction();
  assert(t.calls.includes('cancel-search'));
  assert(!t.calls.includes('clear-destination'));
  assert(!t.calls.includes('stop-guidance'));
});
check('X during running lookup preserves active navigation', () => {
  const t = make({navigating:true,transitNavigation:{routeIndex:0},
                 routeResponse:{routes:[{}]}});
  t.openroadPtXAction();
  assert(t.calls.includes('cancel-search'));
  assert(!t.calls.includes('stop-guidance'));
});
check('X cancelled search reports cancellation not no-service', () => {
  const t = make();
  t.openroadPtXAction();
  assert(t.calls.some(x => x.includes('Search cancelled.')));
  assert(!t.calls.some(x => x.includes('No bus journey')));
});
check('X while guiding prompts user, refusal preserves navigation', () => {
  const t = make({transitSearchRequest:0,transitNavigation:{routeIndex:0}});
  t.openroadPtXAction();
  assert(!t.calls.includes('stop-guidance'));
  assert(!t.calls.includes('clear-destination'));
});
check('X while guiding requires explicit confirmation', () => {
  const t = make({transitSearchRequest:0,transitNavigation:{routeIndex:0},
                  window:{confirm:() => true}});
  t.openroadPtXAction();
  assert(t.calls.includes('stop-guidance'));
  assert(!t.calls.includes('clear-destination'));
});
check('Back exits active route point selection without reroute', () => {
  const t = make({routePointSelectionActive:() => true});
  t.openroadPtBackOneScreen();
  assert(t.calls.includes('reset-point'));
  assert(!t.calls.includes('cancel-search'));
  assert(!t.calls.includes('clear-destination'));
});
check('Back closes most recently visible detail sheet only', () => {
  const t = make({el:id=>({classList:{contains:()=>id!=='transitDetailSheet'}})});
  t.openroadPtBackOneScreen();
  assert.deepEqual(t.calls,['show:transitDetailSheet:false']);
});
check('Back closes route planner without destroying journey', () => {
  const t = make({routePlannerIsOpen:()=>true});
  t.openroadPtBackOneScreen();
  assert.deepEqual(t.calls,['close-planner']);
});
check('Back while searching cancels just the foreground search', () => {
  const t = make();
  t.openroadPtBackOneScreen();
  assert(t.calls.includes('cancel-search'));
  assert(!t.calls.includes('stop-guidance'));
});
check('Back at root cannot silently close destination/guidance', () => {
  const t = make({transitSearchRequest:0});
  t.openroadPtBackOneScreen();
  assert.deepEqual(t.calls,[]);
});
check('Idle X keeps existing close-destination behaviour', () => {
  const t = make({transitSearchRequest:0,transitNavigation:null});
  t.openroadPtXAction();
  assert.deepEqual(t.calls,['clear-destination']);
});
console.log('STAGED ANDROID UX: ' + passed + ' handler checks passed');
