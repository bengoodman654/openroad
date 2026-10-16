# OpenRoad 0.6.13

- Added the private **OpenRoad Transport Server** as the primary English bus timetable router outside London.
- Normal public-transport searches no longer require the phone to download and parse the regional BODS GTFS archive when the server is configured.
- The existing on-device BODS router remains an automatic fallback if the private server is unavailable.
- TfL remains the direct official planner for London.
- Live BODS enrichment remains asynchronous and cannot hold up the initial timetable result.
- Added the private server URL and a masked/revealable server token to Settings.
- Version and user-agent strings updated to 0.6.13.
