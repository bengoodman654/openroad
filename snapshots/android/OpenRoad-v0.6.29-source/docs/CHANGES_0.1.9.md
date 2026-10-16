# ClearRoute 0.1.9

- Restores the exact voice-selection behaviour used in v0.1.6: ClearRoute requests `Locale.UK` and then leaves the selected Android TTS engine to choose its own default UK-English voice.
- Removes the v0.1.8 automatic voice-scoring logic (`getVoices()` / `setVoice()`), plus the forced speech-rate and pitch adjustments, because these could select a poorer offline voice on older Samsung devices.
- Retains the v0.1.8 dedicated map colours, stronger peripheral edge flash, closer/lower navigation camera and directional location marker.
- Keeps the Android voice-settings shortcut, so the phone's default TTS voice can still be changed at system level if desired.
