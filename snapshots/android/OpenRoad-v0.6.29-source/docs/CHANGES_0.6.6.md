# OpenRoad 0.6.6 changes

## Official-data-first public transport

- Added `TransitClient` as the public-transport broker.
- London-to-London journeys prefer the official TfL Journey Planner when a TfL key is configured.
- TransportAPI remains available as the GB-wide multimodal planner/fallback rather than being treated as the main live-data source.
- Added official BODS SIRI-VM live vehicle-position enrichment for English bus legs and bus-number searches.
- Added DfT regional BODS/GB GTFS schedule caching for bus-number route geometry and scheduled stops. The relevant regional ZIP is downloaded on demand, kept in Android cache, and refreshed after 24 hours.
- Bus-number lookups disambiguate common route numbers by selecting the matching GTFS geometry closest to the current location.
- Added National Rail Darwin enrichment for rail legs: official live departure prediction, platform, cancellation and delay information where credentials and a CRS station code are available.
- Added on-demand NaPTAN ATCO-area caching for stop/station reference data.
- Genuine live predictions are labelled `Live`; schedule-only times remain `Scheduled`; mixed itineraries are labelled `Mixed live/scheduled`.
- A fresh BODS vehicle position is not falsely converted into an ETA. Scheduled departure time remains scheduled unless a prediction source supplies a predicted time.

## Settings and credential handling

- Split the former ambiguous API settings into separate TomTom and public-transport provider sections.
- TomTom now shows a masked configured key with Show / Hide / Change controls.
- Added clearly-labelled settings for NaPTAN, DfT/BODS, TfL, National Rail Darwin and TransportAPI fallback.
- Public-transport secret credentials are stored with Android Keystore. Only the non-secret TransportAPI app ID remains in ordinary preferences.
- Existing plaintext TransportAPI keys from the prior build are migrated into secure storage on startup.
- The Settings page explains which sources are built-in, which unlock live data, and which are fallbacks.

## Bus route map

- `bus <number>` search can display DfT scheduled route geometry outside London without spending a TransportAPI request.
- When a BODS key is configured, fresh official live bus positions are overlaid on the scheduled route.
- TfL remains the direct route source in London when configured.

## Identity/version

- Version increased to 0.6.6 / versionCode 66.
- Android application ID remains `uk.co.bengoodman.clearroute` intentionally so this installs as an update over the existing app and preserves local data.
