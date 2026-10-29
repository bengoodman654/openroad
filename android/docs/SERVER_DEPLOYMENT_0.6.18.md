# OpenRoad 0.6.18 server requirement

OpenRoad 0.6.18 is designed to pair with **OpenRoad Transport Server v0.2.2**.

Existing v0.2.1 users should install the v0.2.2 upgrade files, run `upgrade_0_2_2.php`, then rebuild the `south_west` dataset once so full BODS route-shape points are stored. No re-pairing is required.

The server keeps South West permanently prepared. Other English BODS regions are queued only by a destination, a manual preload request, or the optional daily location check, and expire after 60 days of non-use. London remains direct through TfL.
