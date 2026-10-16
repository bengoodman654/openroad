# ClearRoute 0.2.2

## Map palette rebuilt

The previous runtime recolouring approach has been removed. Android Studio now downloads the current OpenFreeMap Positron style during the build, applies the ClearRoute palette to that JSON, validates that road/green/water layers were actually found, and packages the resulting `clearroute-style.json` inside the APK.

The map loads that local style directly. Parks, grass/farmland/woodland, water and the road hierarchy are therefore coloured before MapLibre renders the first frame. Relevant base layers are explicitly made visible.

If OpenFreeMap changes its schema so the expected layers cannot be found, the Android build now stops with an error instead of silently shipping the normal grey Positron map.

The intended palette remains:
- parks/grass/farmland/woodland: light greens
- water/waterways: light blues
- minor roads: pale yellow
- tertiary/secondary/primary/trunk roads: progressively stronger yellows/gold
- motorways: blue with darker blue casings
