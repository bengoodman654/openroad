# ClearRoute v0.6.4

## Interface and map
- Restored the main search placeholder to **Where to?**.
- Map POI labels can be tapped; ClearRoute follows up with TomTom search metadata and shows category, phone and website when available.
- Starred destinations use a filled star state and starred places are rendered as labelled stars whenever the Places layer is enabled.
- Live traffic is independent of travel mode and stays visible whenever the Traffic layer is enabled.
- The current-location control becomes a larger, high-z-index recentre control after a deliberate map pan during navigation.

## Routes
- Driving asks TomTom for the fastest route plus two live alternatives and also tries a no-current-traffic baseline and a motorway-heavy OSM/Valhalla candidate. ClearRoute displays up to three distinct routes; a provider cannot manufacture a genuinely different route where the network has none.
- Walking and cycling request two Valhalla alternatives in addition to the recommended safety/comfort-biased route.
- Route options now include **Prefer motorway-heavy routes**, mutually exclusive with Avoid motorways.

## Public transport
- Added a fourth **Transit** route mode using TransportAPI's UK multimodal Journey Planner.
- TransportAPI app_id/app_key can be entered under Settings > Routing & services.
- Public-transport routes are shown on the map with up to three alternatives and leg summaries. The Journey button opens the itinerary rather than pretending ClearRoute can provide road-style turn-by-turn guidance aboard buses/trains.
- Bus-number searches now expose a bus-service action, but a reliable current bus-number route map is deliberately not claimed as complete yet. The intended robust implementation is the planned BODS/server data layer, rather than guessing provider/operator IDs from a line number.

## Search and contacts
- Optional Android Contacts access can be enabled. Only contacts with postal addresses are returned, and name matches appear above ordinary online suggestions.
- ClearRoute reads contact names/addresses locally; only the address of a contact the user taps is sent to TomTom for geocoding.

## Along-route search
- Along-route POIs are rendered as map markers with their added journey time above each marker. Tapping a marker adds it as the intermediate stop while retaining the original destination.
