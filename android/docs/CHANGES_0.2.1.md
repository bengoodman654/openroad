# ClearRoute 0.2.1

Targeted reliability update after first v0.2.0 device test.

## Voice guidance
- Navigation speech now waits for `TextToSpeech.OnInitListener` to report success before an announcement can be marked as delivered.
- Failed `speak()` queue requests are retried on subsequent location updates instead of being silently consumed.
- TTS output is explicitly tagged as Android navigation-guidance speech.
- Utterance progress/error logging is available under `ClearRouteTTS` without logging location coordinates.

## Map palette
- Corrected vector geometry filters to support Polygon/MultiPolygon and LineString/MultiLineString, matching OpenFreeMap/Positron's own style conventions.
- Repaints Positron's existing park, water, woodland and road layers as a reliable baseline.
- Adds class-specific OpenMapTiles overlays for farmland, grass and the road hierarchy.
- Keeps blue motorways, graded yellow A/B/local roads, pale-blue water and light-green land cover.
