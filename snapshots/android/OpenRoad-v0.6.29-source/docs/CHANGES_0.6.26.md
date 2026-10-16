# OpenRoad 0.6.26 – signed GitHub update support

- Checks GitHub Releases at most daily on app start; includes manual check in Settings > App updates.
- Fetches `update.json` only from the public `bengoodman654/openroad` repository.
- Verifies APK SHA-256 and the certificate of the currently installed application before presenting Android's installer.
- Uses Android FileProvider and only requests unknown-app installation permission on a direct user action.
- Retains Phase 1 search watchdog from v0.6.25.
