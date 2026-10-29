# OpenRoad v0.6.21

## Navigation control follow-up
- Keeps all v0.6.20 lock-screen navigation persistence changes.
- The single Centre/Recentre location control now moves into the right-hand navigation control stack while navigation is active.
- The Recentre control therefore inherits the same 48 px hit area and 10 px spacing as the other navigation buttons and cannot overlap the 2D/3D or route controls on shorter phone viewports.
- Recentre remains a plain blue dot with no direction tail.
- Layers/Places remains available in drive, cycle, walk and public-transport navigation.

## Source hygiene
- Adds the missing `.gitignore` so `local.properties` really is ignored by Git.
- Adds `local.properties.example` with empty credential fields.
- Source distribution omits the private `local.properties`; an existing personal build can copy that file across locally.
- Adds the missing server deployment note. No server change is required from Transport Server v0.2.2.
