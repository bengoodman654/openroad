# ClearRoute 0.1.10

## Navigation voice selection

- Adds **Settings → Navigation voice**.
- Lists installed Android text-to-speech engines visible to ClearRoute, including Google/Samsung/other engines when installed.
- Lets the user choose an engine explicitly instead of relying on Android's implicit/default binding.
- After choosing an engine, lists that engine's English voices, with UK-English voices sorted first.
- Adds **Preview voice**, using a sample navigation instruction before saving.
- Stores only the chosen engine package name and voice name in ClearRoute's local SharedPreferences.
- `NavigationService` now constructs `TextToSpeech` with the selected engine package and uses `setVoice()` for the exact saved voice.
- If the chosen engine is no longer available or cannot start, ClearRoute falls back once to Android's system-default TTS engine.
- Adds the Android 11+ TTS service package-visibility query required for discovering installed engines.

## Press-and-hold map destination

- Press and hold one finger on the map for about 650 ms to create a **Dropped pin** destination at that exact coordinate.
- Moving the finger more than a small tolerance cancels the long press so ordinary panning remains usable.
- The dropped pin uses the normal ClearRoute destination flow: **Directions → choose route → Start navigation**.
- While testing with a mouse, right-clicking the map performs the same dropped-pin action.
- Long-press destination selection is disabled during active navigation; end the current navigation before choosing a new destination.
