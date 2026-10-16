# ClearRoute v0.5.0

## Active-travel routing rebuilt

Walking and cycling no longer use TomTom's generic pedestrian/bicycle fastest-route mode and no longer contain hand-written Bristol exclusions.

They now use Valhalla over OpenStreetMap data with mode-specific dynamic costing:

- Cycling heavily penalises ordinary roads (`use_roads` near zero), favours living streets and usable tracks, discourages hills and poor surfaces, and uses a hybrid/city bicycle profile.
- Walking favours walkways and pavements using sub-1.0 cost factors and heavily penalises driveways, alleys and service access.
- A slightly longer dedicated path can therefore beat a shorter road-heavy route.
- The manual **Avoid road ahead** action is preserved generically by converting the temporary avoided area into a Valhalla avoid location.
- The public FOSSGIS Valhalla service is identified with an X-Client-Id and requests are throttled to roughly one per second.
- There is intentionally no silent fallback to TomTom for walking/cycling if the active-travel service fails: ClearRoute reports the failure rather than knowingly substituting a route with different safety preferences.

This is a routing preference system, not a safety guarantee. OSM access/closure data can still be incomplete or stale.

## UI clean-up

- Drive / Cycle / Walk are compact icon-only controls.
- The main location control visually matches the blue map position dot.
- A separate Recentre button has been removed. During navigation the normal location button appears only after the user pans/zooms away and then recentres the guidance camera.
- Long-pressing the map drops the destination pin without showing a redundant confirmation toast.
- Settings are grouped more clearly and the Done button remains fixed at the bottom while settings content scrolls.
