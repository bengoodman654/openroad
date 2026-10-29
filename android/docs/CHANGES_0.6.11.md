# OpenRoad 0.6.11

## Public transport: TransportAPI no longer required

- Added an on-device DfT/BODS GTFS journey planner for English bus journeys outside London.
- The local planner finds direct buses and one same-stop interchange, honours the walking limit, walking speed, transfer-caution setting and Quickest/Balanced/Fewest changes ranking.
- Walking access/egress is estimated locally; bus timetable times and stops come from the official BODS GTFS schedule.
- BODS SIRI-VM live vehicle positions still enrich scheduled bus legs when the configured BODS key is available.
- TfL remains the direct official journey planner for journeys wholly inside Greater London.
- TransportAPI is now an explicit optional fallback, disabled by default. Its credentials may remain stored, but OpenRoad does not call it unless the user turns on the fallback in Public transport settings.
- Added a clear error when an area or mode is not yet covered by the local official-data planner rather than silently depending on TransportAPI.

## Scope

The new local planner currently covers English bus journeys outside London. Rail timetable journey assembly and regional Scotland/Wales planners remain future official-data layers; Darwin continues to be used for live rail enrichment once credentials are available.
