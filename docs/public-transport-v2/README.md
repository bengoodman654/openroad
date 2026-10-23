# OpenRoad Public Transport v2.2: audited integration contract

Design-only branch. The current OpenRoad Android and PHP production code is unchanged.

Seven corrected vector diagrams, a 56-page authoritative dossier, a correction register for 28 findings, and the complete 105-case acceptance matrix accompany this revision as conversation artefacts.

## Normative design
1. Four independent tasks: journey, service, departure board, map exploration. No journey endpoints for service lookup.
2. Explicit place > selected pin > viewport > GPS **only** when My location was explicitly requested.
3. Assert only licensed, validated provider/mode/area/date capabilities.
4. Stable namespaced operator, line, pattern, trip occurrence and stop IDs; never equate distinct operators by public line number.
5. Pin one immutable schema-compatible timetable snapshot for every complete routing task.
6. Calendar-valid whole journeys; offset-aware UTC events and UK service-date semantics; no automatic relaxation of access constraints.
7. Live/estimated/observed/stale/cancelled are separate states; absent realtime never removes schedules; verified cancelled service is not selectable.
8. Persistent Back arrow at left and X in the right end of the main Where to? field. X priority: dirty-edit confirmation, foreground cancel, visible-guidance Stop confirmation, selected-task close, disabled empty root.
9. Request IDs, generation and pinned snapshot reject all late or mismatched results. Local cancel immediately; remote cancel scoped/authenticated/cooperative; never kill shared imports/workers.
10. Heavy indexing off JustHostMe; signed/staged/validated snapshots, resource gates, atomic switch, rollback and previous-snapshot retention.
11. Release gates cover all enabled P0 cases plus measured shared-host limits and security. A Bristol/Coventry bus pilot cannot claim UK-wide multimodal coverage.

## Test status
The included unittest suite exercises *synthetic reference models* of these rules. It is not an Android or PHP integration test and makes **no external requests**. **0/105 production acceptance cases have passed**. All real golden fixtures, providers, permits and load benchmarks must be verified before enabling any new capability.

See the downloadable v2.2 specification bundle for the complete vector diagrams and 105-row case matrix.
