# OpenRoad Transport Server v0.2.5

See PHASE2_0.2.5.md for BODS on-demand gateway and resource limits.

# OpenRoad Transport Server v0.2.3

See `PHASE1_0.2.3.md` for current changes and safe deployment notes.

Private, single-owner timetable service for OpenRoad 0.6.18.

## v0.2.2 highlights

- South West stays **permanently prepared** and is refreshed from official DfT/BODS GTFS.
- Other English regions are prepared only after OpenRoad sees a destination there, a manual preload request is made, or the optional once-daily location check finds the phone there.
- Temporary prepared regions are retained for 60 days after last use, then can be removed automatically.
- London is deliberately not mirrored: OpenRoad uses TfL directly.
- Journey calculation is staged: a fast direct-route pass returns first, then a fuller transfer search can refine the choices.
- Journey responses are cached briefly, and stop-time queries use an additional covering index.
- Route identity includes the actual trip/departure, preventing async result refinement from changing the map beneath a selected card.
- Full BODS shape points are imported. Exact bus geometry is used where BODS supplies a shape; fallback stop-to-stop geometry is explicitly marked approximate.
- Bus stops on the selected journey are queryable through `/api/v1/stop.php`.
- Bus service route/timetable data remains separate from live vehicle requests so the route appears first.

The service retains the v0.2.x device-key authentication model: HTTPS POST, Android Keystore signing, nonce/replay protection, rate limits, and private files outside `public_html`.

For an existing v0.2.1 installation use `UPGRADE_FROM_0.2.1.md`. Do **not** overwrite your existing `config.php` or re-pair the phone.
