# ClearRoute 0.1.6

## Driving route choices
- The primary driving route remains TomTom `routeType=fastest` with live traffic enabled.
- ClearRoute now also calculates one fastest baseline route with current traffic disabled. When its geometry differs materially from the live route it is shown as **Usual route**. This makes it obvious when live incidents/closures are causing a diversion away from the route a driver would normally expect.
- Up to three choices are displayed: **Fastest now**, **Usual route** (when different), and live-traffic alternatives.
- Requests include TomTom `importantRoadStretch` sections so route cards can show major roads such as `M5 · M42` when the API supplies them.
- Automatic rerouting during navigation still asks only for the current fastest route, avoiding the extra baseline request on every reroute.

## Navigation alerts
- Adds **Settings → Navigation alerts** with three modes: **Voice announcements**, **Flashing screen edges**, and **Silent**.
- Voice remains the default.
- Fixes the early-announcement state machine: the previous code could mark an instruction as seen before it was close enough to speak, which meant only the final near-turn announcement might be heard.
- Edge-flash mode gives two brief amber edge pulses at the same early/near manoeuvre thresholds without speaking.
- ClearRoute keeps the screen awake while active navigation is running so visual alerts remain useful when the phone is mounted.

## Map compass
- The small bottom-left MapLibre control remains the compass/rotation control. It indicates map bearing and returns the map to north-up when tapped.
