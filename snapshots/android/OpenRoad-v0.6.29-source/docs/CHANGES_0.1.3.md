# ClearRoute 0.1.3

- Explicitly enables Android `BuildConfig` generation in `app/build.gradle`.
- Fixes compilation error in `MainActivity.java` at `BuildConfig.DEBUG` under Android Gradle Plugin 8.8.2.
- Keeps WebView remote debugging limited to debug builds rather than enabling it in release builds.
