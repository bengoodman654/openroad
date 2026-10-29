#!/usr/bin/env python3
"""Checks v0.2.9 production router and signed v1 API are kept intact."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
router=(root/"private/lib/router.php").read_text()
api=(root/"public/api/v1/journeys.php").read_text()
assert "or_active_boardings(" in router
assert "or_active_arrivals(" in router
assert "or_trip_stop_matches(" in router
assert "or_first_leg_seeds(" in router
assert "or_second_leg_candidates(" in router
assert "openroad_require_signed" in api
assert "openroad_plan_bus(" in api
assert "v2" not in api, "Legacy live public endpoint must not route research tasks"
print("PASS actual production v0.2.9 router and signed journey endpoint invariants")
