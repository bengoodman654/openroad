# OpenRoad 0.6.18

Paired with OpenRoad Transport Server v0.2.2.

- Permanent South-West preparation plus destination-triggered, manual and optional once-daily preparation of temporary regions.
- Daily area preparation is skipped while either road navigation or public-transport navigation is active.
- Background preload coordinates are rounded to a coarse ~1 km grid before being sent to the private server.
- The daily preload alarm is restored after reboot/app update.
- Route selection is preserved by a stable journey ID while the fast result is replaced by the fuller async result set.
- Starting public-transport navigation removes all alternative route layers and later live/geometry updates no longer redraw them.
- Selected bus stops can be tapped for upcoming services; tapping a service opens its route/timetable.
- Bus service pages load route/timetable first. Live buses remain explicitly optional and, when opened from a stop, show at most the nearest three vehicles whose heading is towards that stop.
- BODS full shape geometry from server v0.2.2 is used for bus legs where available; approximate fallback geometry is labelled as such. Walking geometry continues to refine asynchronously over the pedestrian router.
- Places is now a category chooser for starred places, contacts, pubs/bars, restaurants, cafés, supermarkets and petrol stations. Public categories refresh only for the visible map area.
- A manual Public transport > Prepared areas control can queue a town/postcode for preparation in advance.
- Initial public-transport results remain limited to three with Load 3 more.
