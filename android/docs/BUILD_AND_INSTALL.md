# Build and install OpenRoad 0.6.26

1. Open the **OpenRoad** folder in Android Studio.
2. Allow Gradle sync to finish. The first build needs an internet connection because Gradle downloads Android dependencies and a pinned copy of MapLibre GL JS 5.24.0.
3. Connect the Android phone with USB debugging enabled and accept the phone's **Allow USB debugging** prompt.
4. Select the phone in Android Studio's device selector.
5. Press **Run ▶** to build, install and launch OpenRoad directly on the phone.

Alternatively use **Build > Build APK(s)** and install the generated debug APK manually.

## First launch

OpenRoad should ask for location permission. This personal build already contains the TomTom API key and seeds it into Android Keystore on first launch, so there should be no TomTom setup prompt unless the bundled key is removed.

The base map does **not** need a TomTom key; it uses OpenFreeMap. Search, traffic-aware routing and TomTom traffic layers do need the TomTom key.

## If the map is still blank

Run the app from Android Studio and open **Logcat**. Filter for:

`ClearRouteWeb`

The app now forwards WebView/MapLibre console messages to Logcat, which should expose the exact map-loading problem instead of failing silently.


## Public transport setup

OpenRoad can use free/official data without configuring every provider. DfT GTFS scheduled bus-route data and NaPTAN reference data are downloaded and cached automatically when needed. Optional credentials in **Settings > Routing & services** unlock the following live/direct sources:

- **BODS:** live English bus vehicle positions.
- **TfL:** direct London journey planning and route data.
- **Rail Data Marketplace · Live Departure Board:** official Darwin live GB train predictions, platforms, delays and cancellations. Enter the subscription Consumer key; the legacy Darwin username/password is not used by v0.6.26.
- **TransportAPI:** GB-wide multimodal journey-planning fallback.

The app clearly labels scheduled information separately from genuine live predictions. Provider secrets are stored via Android Keystore.


## Private transport server pairing

The private transport server is optional until it is deployed. OpenRoad uses the slower on-device BODS planner when it is not paired.

After deploying **OpenRoad Transport Server v0.2.0**, run its `private/bin/setup.php` command in cPanel Terminal. The command prints a one-time pairing code. In OpenRoad go to **Settings > Routing & services > OpenRoad private transport server**, enter the code and tap **Pair this phone**.

The pairing creates a device-specific EC key in Android Keystore. The private key is never exported or copied into the source/APK.
