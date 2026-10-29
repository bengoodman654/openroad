# OpenRoad 0.6.8

## Public transport UI

- Added the three-way **Quickest / Balanced / Fewest changes** results control.
- Public-transport results are now vertical cards with departure/arrival time, duration, change count, live/scheduled quality and colour-coded leg chips.
- Transport colours are consistent between the results list and the map. The selected journey uses saturated colours; alternatives use desaturated versions of the same mode colours.
- Tapping a result changes the selected map route without opening details.
- Each result has a separate information button which opens a map-friendly bottom sheet with stop/station names, platforms, stop counts where supplied, live/scheduled provenance and per-leg times.
- Bus/coach numbers in journey cards and details are interactive and open the service view.
- Public-transport results, journey details and bus-service sheets can be minimised/restored by tapping their top handle.

## Journey planner

- Added an **Add stop** control to the public-transport planner.
- Added stops are real routing waypoints, not visual-only fields. OpenRoad calculates each leg between successive via points and combines the segments into whole-journey alternatives.
- Added a public-transport settings sheet with mode checkboxes (all enabled by default), maximum walking, walking speed, connection-buffer preference and accessibility preference.
- Mode and walking limits filter the displayed alternatives; supported provider-side restrictions are also sent with each new search. TfL receives mode, walking-speed, maximum-walking and step-free preferences; TransportAPI receives the selected supported modes. The Balanced ranking also applies a stronger transfer penalty when Cautious connections are selected.

## Bus service view

- Bus route geometry is shown in bus red with stop dots rather than mode icons.
- Up to the three closest fresh live bus positions are drawn when BODS supplies coordinates.
- BODS GTFS now extracts a current-day timetable at the nearest stop using `calendar.txt` / `calendar_dates.txt`, `trips.txt`, `stop_times.txt` and `stops.txt`.
- In London, the TfL service view augments route geometry with live arrivals at the nearest route stop where TfL provides them.
- The service view has Timetable, Stops and About tabs plus a Back button that restores the previous journey-results/detail state.

## Credentials and reliability

- Bundled personal credentials now include the supplied BODS, TfL and TransportAPI credentials and are seeded into Android Keystore on first use.
- National Rail Darwin remains unconfigured until account approval is received.
- The bundled TomTom credential is re-seeded once in v0.6.8 to repair installs that retained a stale encrypted value during the earlier settings migration; user changes after this migration are preserved.
- Version bumped to 0.6.8 / versionCode 68.
