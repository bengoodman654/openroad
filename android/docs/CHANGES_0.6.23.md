# OpenRoad v0.6.23

## Route-planning lifecycle

- Cancelling, replacing or recalculating a route now invalidates the native request immediately.
- Public-transport routing has a cancellable active `Future` plus a generation token. Abandoned work is interrupted and every expensive enrichment/segment stage checks the token before continuing or publishing an update.
- Stale timetable/live/geometry callbacks therefore cannot replace a later route after the user has cancelled or moved on.
- Multi-stop public-transport planning uses the private server's fast phase for each segment to get the first combined result on screen sooner; the fuller search/enrichment continues only while that request remains current.

## Route points

- The start point in the top route planner is now editable. `My location` can be replaced with any searched place for planning journeys away from the phone's current position.
- Choosing `My location` again restores live-position routing.
- Added stops can be tapped to replace them and dragged with a dedicated grip to reorder them.
- The destination can be changed from the same route-point list without discarding the chosen start point or added stops.
- The route-point rows have been simplified to reduce visual clutter.

## Public-transport sheet

- Increased the space between the minimise handle and Drive / Cycle / Walk / Transit controls when the transit sheet hides its normal header. This reduces accidental minimisation while switching mode.

## Places

- Moved the Places close button further into the top-right corner.
- Expanded map-place categories from the original small set to include bakeries, takeaways, shopping centres, cash machines, post offices, pharmacies, EV charging, parking, railway stations, bus stops, public toilets, hospitals, hotels, parks, playgrounds, gyms, libraries and cinemas.
- Categories are grouped into Personal, Food & drink, Shopping & services, Transport and Useful nearby sections.

## Version

- Android source version: **0.6.23** (`versionCode 83`).
- No OpenRoad Transport Server change is required; this build remains compatible with server v0.2.2.
