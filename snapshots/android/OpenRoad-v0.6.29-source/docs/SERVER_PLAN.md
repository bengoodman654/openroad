# ClearRoute server plan

The personal JustHostMe account should **not** proxy OpenFreeMap vector tiles. The public OpenFreeMap service is already specialised for serving static vector tiles, and an extra shared-hosting hop would normally add latency rather than improve it.

The server remains useful for a later data-enrichment layer:

1. Receive/cache UK roadworks and temporary-closure feeds (DfT Street Manager, National Highways, devolved feeds as appropriate).
2. Normalise those different feeds into one small ClearRoute JSON format.
3. Optionally proxy commercial API requests if hiding the TomTom key from the APK becomes more important than the extra network hop.
4. Never store route history or raw GPS tracks by default.

This keeps the phone-to-map path direct and fast while using the server only where it provides a real privacy/data-quality advantage.
