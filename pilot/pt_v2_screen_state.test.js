'use strict';
const assert = require('node:assert/strict');
const {PTScreenState} = require('./pt_v2_screen_state.js');

let passed = 0;
function test(name, fn) {
  fn();
  passed++;
  console.log('PASS', name);
}
const a = 'opaque-request-0001';
const b = 'opaque-request-0002';
const envelope = (t, results) => ({
  requestId: t.taskId, generation: t.generation,
  outcome: 'OK', results
});
const options = [
  {id: 'routeA', selectable: true},
  {id: 'routeB', selectable: true},
  {id: 'research-only', selectable: false},
];

test('back and X placement are persistent in Where to controls', () => {
  const s = new PTScreenState();
  assert.equal(s.controls().xPlacement, 'WHERE_TO_RIGHT');
  assert.equal(s.controls().xVisible, true);
  assert.equal(s.controls().xEnabled, false);
  s.pushScreen('PREFERENCES');
  assert.equal(s.controls().backEnabled, true);
});

test('X cancels foreground lookup but preserves existing guidance', () => {
  const cancels = [];
  const s = new PTScreenState(ticket => cancels.push(ticket));
  s.setGuidance('existing-route');
  const t = s.beginSearch(a);
  assert.equal(s.x().action, 'CANCEL_FOREGROUND');
  assert.equal(s.guidanceId, 'existing-route');
  assert.deepEqual(cancels, [t]);
  assert.equal(s.receive(envelope(t, options)), false);
});

test('X after search completed requires confirmation to stop guidance', () => {
  const s = new PTScreenState();
  s.setGuidance('existing-route');
  const t = s.beginSearch(a);
  assert.equal(s.receive(envelope(t, options)), true);
  assert.equal(s.x().action, 'CONFIRM_STOP_GUIDANCE');
  assert.equal(s.confirmStopGuidance(false), false);
  assert.equal(s.guidanceId, 'existing-route');
  assert.equal(s.confirmStopGuidance(true), true);
});

test('new generation cancels and fences old results', () => {
  const cancels = [];
  const s = new PTScreenState(ticket => cancels.push(ticket));
  const old = s.beginSearch(a);
  const current = s.beginSearch(b);
  assert.deepEqual(cancels, [old]);
  assert.equal(s.receive(envelope(old, options)), false);
  assert.equal(s.receive(envelope(current, options)), true);
  assert.equal(s.displayTicket.generation, 2);
});

test('repeat X cannot double-send a cancellation', () => {
  const cancels = [];
  const s = new PTScreenState(ticket => cancels.push(ticket));
  s.beginSearch(a);
  assert.equal(s.x().action, 'CANCEL_FOREGROUND');
  assert.equal(s.x().action, 'NO_ACTION');
  assert.equal(cancels.length, 1);
});

test('failed remote cancel never resurrects old local results', () => {
  const s = new PTScreenState(() => { throw new Error('network down'); });
  const t = s.beginSearch(a);
  s.x();
  assert.equal(s.remoteCancelErrors.length, 1);
  assert.equal(s.receive(envelope(t, options)), false);
});

test('late enrichment preserves selected itinerary and camera position', () => {
  const s = new PTScreenState();
  const t = s.beginSearch(a);
  s.receive(envelope(t, options));
  assert.equal(s.userSelect(t, 'routeA'), true);
  const camera = s.cameraEpoch;
  assert.equal(s.enrich(t, 'routeB', {geometry: [1,2]}), false);
  assert.equal(s.enrich(t, 'routeA', {geometry: [2,3]}), true);
  assert.equal(s.selectedId, 'routeA');
  assert.equal(s.cameraEpoch, camera);
});

test('only a deliberate tap changes selected alternative and camera', () => {
  const s = new PTScreenState();
  const t = s.beginSearch(a);
  s.receive(envelope(t, options));
  s.userSelect(t, 'routeA');
  const epoch = s.cameraEpoch;
  assert.equal(s.userSelect(t, 'routeB'), true);
  assert.equal(s.selectedId, 'routeB');
  assert.equal(s.cameraEpoch, epoch + 1);
});

test('research-only unselectable itineraries cannot start guidance', () => {
  const s = new PTScreenState();
  const t = s.beginSearch(a);
  s.receive(envelope(t, options));
  assert.equal(s.userSelect(t, 'research-only'), false);
});

test('Back pops one screen and cancels only owned child lookups', () => {
  const s = new PTScreenState();
  s.setGuidance('old-guidance');
  s.pushScreen('RESULTS');
  s.pushScreen('BUS_DETAILS');
  s.registerChildRequest('BUS_DETAILS', 'departures-request');
  s.registerChildRequest('RESULTS', 'route-enrichment');
  const first = s.back();
  assert.equal(first.screen, 'BUS_DETAILS');
  assert.deepEqual(first.cancelChildren, ['departures-request']);
  assert.equal(s.guidanceId, 'old-guidance');
  assert.equal(s.stack.length, 2);
});

test('dirty route edit prompts keep or discard instead of silently leaving', () => {
  const s = new PTScreenState();
  s.pushScreen('ROUTE_EDIT');
  s.dirtyEdit = true;
  assert.equal(s.back().action, 'CONFIRM_DISCARD_EDIT');
  assert.equal(s.resolveDirtyEdit(false).action, 'KEEP_EDITING');
  assert.equal(s.stack.at(-1), 'ROUTE_EDIT');
  assert.equal(s.resolveDirtyEdit(true).action, 'POP_ONE');
  assert.equal(s.stack.at(-1), 'PT_ROOT');
});

test('X closes idle result but does not terminate underlying guidance', () => {
  const s = new PTScreenState();
  const t = s.beginSearch(a);
  s.receive(envelope(t, options));
  assert.equal(s.x().action, 'CLOSE_RESULT');
  assert.equal(s.displayTicket, null);
});

console.log('OpenRoad PT v2 screen-state: ' + passed + ' checks passed.');
