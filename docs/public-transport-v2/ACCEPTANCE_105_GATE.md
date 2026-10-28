# OpenRoad public transport v2 — 105-case release acceptance gate

The manifest at pilot/acceptance_cases_105.json identifies 105 separate
requirements across timetable, regional coverage, direct journeys,
transfers, pedestrian routing, rail, realtime, cancellation, UI,
route semantics, latency, offline operation, security, deployment and
accessibility.

None of these 105 integrated/field acceptance cases is independently
approved as of 28 October 2026. The synthetic regression suite and
successful October Bristol route test are valuable evidence, but
cannot satisfy all these end-to-end scenarios.

The acceptance_gate.py tool requires build/version, source snapshot,
independent verification method, evidence URL and reviewer. Unit-test
results alone cannot promote a production case.

Bristol and Coventry OSM exact stop-code audits found many coincident
NaPTAN identifiers, but ZERO independently reviewed pavement-side
connectors; the new gate rejects unverified transfer paths.

The full production release remains blocked on real phone, multiple
regional timetables, verified walking access and rail/live source rights.
