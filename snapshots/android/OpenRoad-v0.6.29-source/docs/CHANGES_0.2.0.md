# ClearRoute 0.2.0

A consolidation release following a full code/usability audit rather than a single-feature patch.

## Most important user-visible change
The missing visual navigation path is repaired. Bearing information now reaches the map, navigation enters a dedicated guidance UI, the map follows heading-up, and a large manoeuvre arrow accompanies the written instruction.

## Other fixes
- route-segment map matching instead of nearest-vertex matching;
- along-route turn distances;
- better remaining-time estimates;
- less trigger-happy rerouting;
- single high-frequency location owner during navigation;
- active-route lifecycle/state synchronisation;
- cache-only recoverable active route;
- persistent traffic/search-bias/travel-mode settings;
- stale route callback protection;
- delayed notification permission request;
- external-link WebView hardening;
- friendlier API errors;
- no precise coordinate diagnostic logging;
- cycleway overlay shown only in Cycle mode;
- simplified cycle/walk alternatives.

See `AUDIT_0.2.0.md` for the complete audit notes.
