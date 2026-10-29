# OpenRoad provider configuration (v0.6.27)

**No private API credential is included in the distributable source ZIP.** Android release builds from this source are safe to publish *only when provider credentials have not been bundled into BuildConfig*. Do not place secrets in the public GitHub repository.

## Provider summary

| Service | Purpose | Need key for current features? | Recommended storage |
|---|---|---|---|
| OpenRoad Transport Server | Fast signed-device timetable search on JustHostMe | No shared API key: existing paired device private signing key | Keep current pairing; no action after in-place update |
| TomTom | Place search, driving routes and traffic | Yes | Enter once in Android Settings → Services & API keys |
| DfT/BODS | Official regional bus schedules and optional live vehicle positions | Not for server timetable data; optional for live positions | Android encrypted settings |
| TfL | London's route planning and live transport information | Anonymous fallback currently exists | Android encrypted settings if you have an app key |
| Rail Data Marketplace (LDBWS) | Live train departure predictions, not point-to-point rail itineraries | Yes to call RDM Live Departure Board | Android encrypted settings, or future private-server proxy |
| TransportAPI | Optional fallback if your subscription includes journey planning | Only if fallback enabled | Android encrypted settings; fallback remains off by default |

### Why provider values were not prepopulated

Previous conversation history and source archives identify providers but do not contain safely retrievable credential values. The original source archives contain `local.properties.example`, not working keys. We cannot infer provider credentials from registered accounts.

An in-place Android update signed with the same certificate retains existing encrypted provider settings. An uninstall destroys app data, including these credentials and the server pairing.

### Important build warning

The GitHub Android workflow currently supports optional `TOMTOM_API_KEY`, `BODS_API_KEY`, `TFL_API_KEY`, `TFL_SECONDARY_API_KEY`, `RAILDATA_API_KEY`, `TRANSPORTAPI_APP_ID` and `TRANSPORTAPI_APP_KEY` secrets. **If any are configured, they are injected into BuildConfig and are extractable from the APK**, including public GitHub releases. For private consumer keys, prefer one-time Android setup and do not bundle them. Merely storing a value in GitHub Secrets does not make it secret once compiled into a public APK.

### Phase 2 rail provider test

The live board check lives in Settings → Services & API keys → National Rail, defaults to station CRS `BRI` (Bristol Temple Meads), and verifies the user-saved RDM consumer key against the official JSON departure-board service. Departure boards do not provide timetable routing, fares or connecting travel legs; implementing these requires separate timetable/journey-planning capabilities.
