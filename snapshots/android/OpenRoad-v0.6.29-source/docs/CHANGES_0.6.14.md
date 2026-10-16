# OpenRoad 0.6.14

- Replaced the reusable bearer token for the private OpenRoad transport server with device-specific request signing.
- OpenRoad now generates an EC P-256 signing key inside Android Keystore. The private key is non-exportable; only the public key is registered with the server.
- Added one-time server pairing. The server generates a short-lived one-time code in cPanel; the code is entered in OpenRoad Settings and becomes invalid after successful pairing.
- Every private-server request is HTTPS POST and signs the method, path, timestamp, nonce, device ID and SHA-256 body hash.
- Added replay protection, clock-skew checks and server-side per-device/rate limiting.
- Journey coordinates are moved from URL query parameters into the HTTPS POST body, so ordinary Apache/LiteSpeed access logs do not contain the coordinates in the URL.
- The server hostname remains discoverable on public DNS, but the document root returns 404 and the API cannot be used without a paired device key.
- Added Settings controls to pair/check/remove the private transport server without exposing any reusable server password.
- The existing on-device BODS journey planner remains an automatic fallback until the private server is paired or whenever it is unavailable.
- Version and user-agent strings updated to 0.6.14.
