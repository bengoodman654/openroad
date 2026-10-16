# OpenRoad v0.6.28 — Rail Data credentials moved to private server

- Rail departure-board test now uses the **same signed, paired-server authentication** as existing bus routes, via `/api/v1/rail.php`.
- No Rail Data consumer key is read from Android for departure boards or bundled into this APK.
- Settings show private server management instead of a rail key-entry form.
- No changes to local bus planner, London TfL, or the other providers yet. Phase 2 transport migration is incremental.
- **Deployment order:** configure and test Transport Server v0.2.4 first, then install this Android update. Without the server endpoint/key, rail departures will show an error. Bus routing remains available.
