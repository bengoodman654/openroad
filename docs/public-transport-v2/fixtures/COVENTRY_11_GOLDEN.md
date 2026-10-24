# Coventry 11 — first official dated source fixture

Status: **source-derived, corroborated at five timetable checkpoints; NOT production acceptance.**

The fixture was extracted from the Department for Transport BODS National Express Coventry dataset 20442, ZIP SHA-256 5fc158d433b7eff9dc72270b8d955d00d4ae2a8e027dbf13bb1316634cec05e0, inner XML file BODS_PD0001111_813_20260920_32.xml.

The specific journey is service 11, operator NOC TCVW, service code PD0001111:813, journey VJ136, pattern JP40, **Friday 23 October 2026**. The operator TXC contains a Monday–Friday regular-day rule for this trip. The selected day was not an England/Wales bank holiday according to https://www.gov.uk/bank-holidays .

The source-derived fixture contains 26 sequential official ATCO stop references and per-stop boarding/alighting activities. A separately displayed timetable at https://bustimes.org/services/11-coventry-university-of-warwick-kenilworth-leami for 23 October 2026 agrees with these five points:

| Stop | ATCO code | Derived time | Published displayed time |
|---|---|---|---|
| University Interchange | 43000065301 | 05:55 | 05:55 |
| Scarman Road | 43001317102 | 05:56 | 05:56 |
| Varsity Pitches | 43000065102 | 05:57 | 05:57 |
| Westwood Campus | 43000063701 | 05:58 | 05:58 |
| Pool Meadow Bus Station | 43000005010 | 06:21 | 06:21 |

Source extraction (bounded to a single XML member): https://github.com/bengoodman654/openroad/actions/runs/40085398121 .

### Design restrictions

Bus Times may ultimately obtain its timetable from the same BODS dataset, so this is a separate presentation check, **not necessarily a statistically independent data source**. Only those five points have been externally compared. The remaining 21 intermediate stop times are source-derived but have not all been manually verified.

The offline pilot engine accepts **only the exact approved source SHA, XML member, trip and 23 October date**. It rejects unsupported dates, wrong operators, reverse-direction journeys, unknown stops, missed departures, invalid offsets and disallowed boarding/alighting. It uses Europe/London timestamps and UTC-based elapsed time arithmetic.

This is deliberately not a countrywide timetable engine. Before offering real passenger routing, implement complete TXC operating-profile inheritance, school and bank holiday exceptions, dead runs, journey pattern overrides, service-day/DST transitions, timetable versioning, transfers, walking geometry and lifecycle cancellation. No Android or production server integration has been exercised.

**Production acceptance remains 0 of 105 cases passed.** All source work was performed off-host; no deployed OpenRoad code was modified.
