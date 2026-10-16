# OpenRoad v0.6.20

## Navigation persistence
- Public-transport navigation now has a native Android foreground location service.
- Transit journey state is stored in the same short-lived active-route store used by road navigation and restores after screen lock/activity recreation.
- Active transit navigation continues to suppress the midday preload check.

## Navigation controls
- Map Layers/Places remains available during drive, cycle, walk and transit navigation.
- Navigation recenter control is now a simple blue location dot with no direction tail.
- Right-side navigation controls use consistent 48dp hit areas and even spacing.
- Primary manoeuvre/distance HUD is larger and more glanceable.

## Audit hardening
- Personal build credentials moved from committed build.gradle constants into git-ignored local.properties.
- Contacts bridge now requires active search text and returns at most eight matching addressed contacts; wholesale address-book enumeration is removed.
- Contact geocoding gets immediate progress feedback.
- System dark mode applies a dark OpenRoad UI and native status/navigation bars without changing MapLibre style/camera state.
- Bottom sheets support drag-to-minimise/restore in addition to tapping.
- Offline state shows a persistent banner while preserving the current cached route where possible.
- Interactive controls receive larger hit areas without making small map markers visually oversized.

## Deliberately not changed
- The top Where to? interaction remains the primary search model.
- Map tiles remain direct rather than being proxied through shared hosting.
