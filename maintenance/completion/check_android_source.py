#!/usr/bin/env python3
"""Baseline assertion to prevent accidental old Android source integration."""
from pathlib import Path
import sys

root=Path(sys.argv[1]); app=(root/"app/src/main/assets/app.js").read_text()
java=root/"app/src/main/java/uk/co/bengoodman/clearroute"
assert java.is_dir()
for file in ["TransitClient.java","MainActivity.java","OpenRoadServerClient.java"]:
    assert (java/file).is_file(), file
assert "openroadPtXAction" in app, "Missing production transit X"
assert "openroadPtBackOneScreen" in app, "Missing production Back flow"
assert "cancelActiveRouteRequest" in app, "Missing local generation cancellation"
assert "routeSearchClearBtn" in app
assert "ptV2Research" not in app, "Unverified research path exposed to user"
source=(java/"TransitClient.java").read_text()
assert "cancelRouteWork" in source
assert "ROUTE_GENERATION" in source
assert "routeWithStops" in source
print("PASS current Android 0.6.32 cancellation and route UI invariants")
