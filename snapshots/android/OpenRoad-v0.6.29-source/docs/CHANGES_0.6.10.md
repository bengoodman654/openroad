# OpenRoad 0.6.10

- Audited every bundled API credential against the values supplied for this personal build.
- One-time credential repair on upgrade: TomTom, BODS, TfL primary/secondary and TransportAPI credentials are re-seeded exactly once, then remain user-editable.
- Added masked credential displays using asterisks plus eye reveal/hide controls.
- Added the TfL secondary subscription key as a stored spare; the primary remains the active key.
- TransportAPI now distinguishes credential failure from plan/product failure. A 403 saying Journey Planner is not part of the plan is reported as a plan limitation, not a bad API code.
- National Rail Darwin remains intentionally unconfigured until credentials are supplied.
