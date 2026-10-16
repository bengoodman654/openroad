# OpenRoad private transport backend

OpenRoad 0.6.14 can use the owner's private cPanel/PHP/MySQL transport server as its primary English-bus timetable router. The deployable package is supplied separately as `OpenRoad-Transport-Server-v0.2.0.zip`.

v0.2.0 uses device-specific ECDSA request signing rather than a bearer token. The Android private key remains in Android Keystore; the server stores only the public key. See `../docs/SERVER_DEPLOYMENT_0.6.14.md`.
