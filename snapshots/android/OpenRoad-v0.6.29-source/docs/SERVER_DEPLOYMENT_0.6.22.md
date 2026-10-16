# OpenRoad 0.6.22 server requirement

OpenRoad 0.6.22 remains compatible with **OpenRoad Transport Server v0.2.2**.

No server file or database update is required when upgrading the Android app from 0.6.21 to 0.6.22.

The Android client now always sends `maxWalk: 999` to the existing server API and always requests three public-transport results. This removes the user-facing walking-limit behaviour while preserving compatibility with the current server contract.
