# OpenRoad 0.6.19

Paired with OpenRoad Transport Server v0.2.2; no server update required.

- Route map now draws only the alternatives actually shown in the route-options panel.
- Alternatives that are substantially slower/longer than the best route are suppressed, so OpenRoad may present one or two sensible routes instead of forcing three.
- Public-transport walking geometry for the selected journey is refined immediately after first paint, before the slower full alternative search.
- Live/geometry updates no longer auto-fit the map; user zoom/pan is preserved.
- Route sheet is substantially more compact; minimised state deliberately exposes the upper part of the travel-mode selector as a clear restore affordance.
- Main Settings is split into category pages: Places & search, Guidance, Map & location, Public transport, Routing, and Services & API keys.
- A dropped pin created while Add stop is active becomes the new intermediate stop instead of replacing the whole destination.
- Public-transport intermediate stops gain drag handles and can be reordered by dragging.
