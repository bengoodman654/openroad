# OpenRoad automated releases

## Android

GitHub Actions builds the newest `OpenRoad-v*-source.zip` uploaded to the repository. It runs source validation and a debug build. Once all signing secrets are configured it also builds a release-signed APK and publishes a GitHub Release with `update.json` and a SHA-256 checksum. The Android app checks for releases daily while open, or when Settings > App updates > Check now is used, and offers Install update.

The signing keystore **must be kept permanently**, backed up securely outside GitHub, and reused for every subsequent version. Android cannot update an installed app signed with a different certificate. An initial Android Studio debug install may require uninstalling and reinstalling from the first signed release, which removes locally stored saved places and API keys. Export/back up your settings before changing certificate.

Generate a new private signing key on a trusted local machine **only if you do not have an existing signing key**:

```bash
keytool -genkeypair -v -keystore openroad-release.jks -alias openroad -keyalg RSA -keysize 3072 -validity 10000
base64 < openroad-release.jks | tr -d '\n' | pbcopy    # macOS: copy keystore to clipboard
```

In GitHub repository Settings > Secrets and variables > Actions > Secrets set:
`ANDROID_KEYSTORE_BASE64`, `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.

Optionally set `TOMTOM_API_KEY`, `BODS_API_KEY`, `TFL_API_KEY`, `TFL_SECONDARY_API_KEY`, `RAILDATA_API_KEY`, `TRANSPORTAPI_APP_ID`, `TRANSPORTAPI_APP_KEY` if you want credentials bundled. The publicly distributed APK contains any bundled values; provider key restrictions and secure settings are essential. Never put keys in repository files.

Upload `OpenRoad-v0.6.26-source.zip` to the repository root. It starts the workflow. When signing secrets have been set, releases are created on each push that changes a versioned source archive. Each release must have a distinct, increasing `versionCode` and `versionName`. Changes to Java files inside a ZIP will not be diffable in the GitHub UI: moving to a normal source tree is strongly recommended later.

The APK is **not silently installed**: Android asks the user to approve it and may require enabling installation from OpenRoad the first time. The updater verifies both its hash and Android signing certificate.

## Transport server

Upload `OpenRoad-Transport-Server-v0.2.3-upgrade.zip` to the repo root. The cPanel workflow verifies PHP syntax. For production deployment, go to Actions > OpenRoad transport server > Run workflow, enter `DEPLOY`, and approve the `openroad-production` environment if you configured reviewers.

Configure secrets `CPANEL_SSH_PRIVATE_KEY`, `CPANEL_SSH_KNOWN_HOSTS`, `CPANEL_SSH_HOST`, `CPANEL_SSH_USER`, and repository variables `CPANEL_OPENROAD_PRIVATE_DIR` (for example `/home/youruser/openroad-private`), `CPANEL_OPENROAD_PUBLIC_DIR` (for example `/home/youruser/public_html/openroad-api`) and optional `CPANEL_SSH_PORT`.

The SSH public key must be authorised on your hosting account, and SSH access must be enabled in cPanel. Obtain and verify the SSH host key out of band; do not accept `ssh-keyscan` output blindly as proof of identity. Use a deploy-only SSH key and least privilege access. Configure an `openroad-production` environment with a reviewer. The workflow backs up existing PHP files, preserves `private/config.php`, database, cache and logs, then replaces only the four allowlisted Phase 1 PHP files. Initial setup and data migrations are manual and are not run by the deployment workflow.

Before enabling automatic production deployments, test the job on a staging directory and confirm the public/private paths. Never expose the private directory under the web root.
