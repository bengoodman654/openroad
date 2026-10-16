# OpenRoad 0.6.7

- Fixed Android compilation failure in `TransitClient.enrichTransportApi` by propagating checked JSON exceptions to the existing route-level error handler.
- TfL Unified API no longer requires a key for normal personal use; anonymous access is used automatically and an app key remains optional for a higher request allowance.
- Added empty personal-build fields for BODS, TfL, National Rail Darwin and TransportAPI credentials so supplied credentials can be bundled and seeded into Android Keystore on first launch, matching the TomTom workflow.
- Explicit Java 17 source/target compatibility removes JDK 25's obsolete Java 8 source/target warning.
- Version bumped to 0.6.7 / versionCode 67.
