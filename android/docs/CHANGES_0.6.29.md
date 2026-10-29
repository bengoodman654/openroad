# OpenRoad v0.6.29 — private BODS gateway

- On-demand live bus requests now go via the signed OpenRoad server API, not directly to BODS from Android.
- No bus key is shipped in Android and users no longer need to enter a BODS key on their phone.
- Scheduled bus routes and national rail departure boards remain unchanged.
- **No automatic BODS requests during journey planning** to protect shared JustHostMe hosting.
- The existing app's TfL, TomTom and optional TransportAPI operations still use their prior behaviour, pending separate migration.
- Requires server v0.2.5 with `bods_api_key` configured privately. Does not alter Android pairing.
