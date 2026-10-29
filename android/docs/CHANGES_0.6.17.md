# OpenRoad 0.6.17

## Map and route presentation
- First usable location fix recentres the opening map at zoom 15.5.
- Initial route lists are capped at three choices. Public transport has **Load 3 more** up to nine.
- Public-transport cards show a small per-route state while walking geometry, bus geometry or live data is still loading; unavailable exact geometry is explicitly marked approximate.
- Walking legs are refined asynchronously through the pedestrian router and their real routed distance/time replaces the straight-line estimate.
- Public-transport bus geometry from the private server uses indexed BODS shapes where available.

## Bus service view
- Bus-number taps use the private indexed server route endpoint first.
- Route, stops and timetable are returned before any live vehicle request.
- Live buses are now an explicit **Live buses** action after the scheduled route is visible.

## Public transport quality audit
- Fixed server nearest-stop selection: v0.2.0 could discard the genuinely nearest stops because SQL LIMIT was applied before geographic sorting.
- Fixed the on-device fallback choosing an unnecessarily upstream boarding stop on the same bus trip; it now favours the reachable stop requiring the least walking.
- Fixed server connection feasibility to match the app: Normal = 3 minutes, Cautious = 8 minutes.
- Fixed route scoring to use actual arrival clock time rather than only in-vehicle/duration totals, so waiting time counts.
- Balanced ranking now gives walking substantial weight while Quickest still prioritises arrival time and Fewest changes strongly prioritises transfers.
- Maximum walking is treated as the whole access + egress walking budget.
- Real pedestrian geometry is used to update walking duration and can invalidate a departure if the true walking path means it is no longer reachable.
- UI re-ranking mirrors the planner's walking/change priorities instead of undoing server ordering.

## UI
- Cycling and walking symbols have been redrawn with clearer conventional silhouettes.
- Public-transport settings are grouped into Allowed transport, Walking, Connections and Advanced fallback.
- The bottom-sheet grab area and the minimised sheet tab are substantially larger.
