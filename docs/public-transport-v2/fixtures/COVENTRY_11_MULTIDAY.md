# Coventry route 11 multi-trip timetable pilot — 24 October 2026

**Design/offline research only. No production Android or server deployment.**

## Official source

DfT BODS operator code TCVW, dataset [20442](https://data.bus-data.dft.gov.uk/timetable/dataset/20442/download/), snapshot SHA-256 `5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0`. Two dated TransXChange members are selected explicitly: revision starting **20 September 2026** for 23–24 October and revision starting **25 October 2026** for 25–26 October. Heavy downloads and XML processing run on disposable GitHub runners with size and checksum limits.

| Service date | Eligible source vehicle-journey records | Exact redundant records | Distinct timetable patterns |
|---|---:|---:|---:|
| Fri 23 October | 204 | 102 | 102 |
| Sat 24 October | 99 | 0 | 99 |
| Sun 25 October | 62 | 0 | 62 |
| Mon 26 October | 106 | 0 | 106 |

All figures are **candidate records** from the source and not confirmed real-time vehicle operations. They do not imply that the whole published timetable is understood. Friday source inspection excluded **54** journey records with unsupported calendars; Monday excluded **19**. Other records correctly did not operate on the selected weekday.

The **102 duplicated Friday entries** differ in source vehicle-journey codes but have exactly the same complete source timetable sequence, stop permissions and direction. The display router now collapses equivalent timetable options while retaining the source trip IDs as aliases for later real-time matching. Distinct intermediate stop patterns are not merged.

## Real-data direct-route dry-run

The offline multi-trip direct router returns up to three timetable candidates for known passenger stops on 23, 24 and 26 October; the run [on GitHub](https://github.com/bengoodman654/openroad/actions/runs/40129631083) verifies the source hash and route outcomes.

**Sunday 25 October 2026 is a UK daylight-saving fall-back date.** Calendar candidate discovery succeeded, but the preliminary router returns the explicit status `UNSUPPORTED_CALENDAR_TIME_TRANSITION`, rather than displaying potentially wrong clock times. It is not yet a supported journey-planning day.

The earlier, much narrower corroborated fixture remains valid: [Coventry 11, Friday 23 October, 05:55 University Interchange to 06:21 Pool Meadow](COVENTRY_11_GOLDEN.md), with five published stop-time checkpoints.

## Mandatory safety and correctness limitations

- These are source-derived **direct bus** trips only, not a transfer or walking planner.
- Full calendar exceptions, school-term/holiday rules, DST time arithmetic, positioning trips, accessibility, real-time matching and all stop-level published-time verification require further work.
- The importer honours route, operator, dated snapshot and ATCO stop identities. It does not infer Coventry from GPS or public line number alone.
- StartDeadRun may be **depot positioning before a valid public trip**, not an instruction to discard that trip.
- Failure statuses distinguish a verified absence from missing calendar interpretation. Unhandled rules must not silently produce `NO_JOURNEY`.
- No complete UK transport source coverage, Android integration or JustHostMe performance testing has been carried out.

Evidence: [all-date source and duplicate audit](https://github.com/bengoodman654/openroad/actions/runs/40129397412); [real dated direct-route dry-run](https://github.com/bengoodman654/openroad/actions/runs/40129631083); [machine-readable evidence manifest](official_coventry_11_multiday_evidence.json).

**Production acceptance: 0 of 105 cases passed.** Passing source-fixture and model-unit tests does not establish production readiness.
