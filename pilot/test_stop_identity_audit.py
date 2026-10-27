"""Synthetic exact-stop identity tests. Never grants pedestrian access."""
import unittest
from datetime import date
from types import SimpleNamespace
from pilot.gtfs_engine import Stop
from pilot.stop_identity_audit import audit_stop_codes


class StopIdentityAuditTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = SimpleNamespace(
            city="Bristol", service_day=date(2026, 10, 26),
            source_sha256="fixture-gtfs",
            stops={"0100A": Stop("0100A", "A", 51.4545, -2.5879)})
        self.graph = SimpleNamespace(
            source_sha256="fixture-osm",
            transit_stops={"1": {
                "atcoCode": "0100A", "lat": 51.4545, "lon": -2.5879}})

    def run_audit(self):
        return audit_stop_codes(self.snapshot, self.graph)

    def test_exact_near_is_never_automatically_verified(self):
        r = self.run_audit()
        self.assertEqual(r["statusCounts"]["EXACT_TAG_NEAR_UNVERIFIED"], 1)
        self.assertEqual(r["autoVerifiedStopAnchors"], 0)
        self.assertFalse(r["usableInRouting"])
        self.assertFalse(r["walkingSafetyConfirmed"])

    def test_same_coordinates_without_exact_code_do_not_match(self):
        self.graph.transit_stops["1"]["atcoCode"] = "OTHER"
        self.assertEqual(self.run_audit()["statusCounts"]["NO_EXACT_TAG"], 1)

    def test_duplicate_code_is_ambiguous_even_if_near(self):
        self.graph.transit_stops["2"] = dict(self.graph.transit_stops["1"])
        self.assertEqual(self.run_audit()["statusCounts"]["DUPLICATE_TAG_REVIEW"], 1)

    def test_far_exact_code_needs_review(self):
        self.graph.transit_stops["1"]["lat"] = 51.4560
        self.assertEqual(self.run_audit()["statusCounts"]["EXACT_TAG_DISTANT_REVIEW"], 1)

    def test_nonfinite_osm_coordinates_cannot_match(self):
        self.graph.transit_stops["1"]["lon"] = float("nan")
        self.assertEqual(self.run_audit()["statusCounts"]["NO_EXACT_TAG"], 1)

    def test_out_of_radius_gtfs_stop_not_counted(self):
        self.snapshot.stops["0100B"] = Stop("0100B", "Far", 51.60, -2.5879)
        self.assertEqual(self.run_audit()["gtfsStopsWithinRadius"], 1)

    def test_case_and_whitespace_normalisation(self):
        self.graph.transit_stops["1"]["atcoCode"] = " 0100a "
        self.assertEqual(self.run_audit()["statusCounts"]["EXACT_TAG_NEAR_UNVERIFIED"], 1)

    def test_empty_inventory_never_grants_access(self):
        self.snapshot.stops.clear()
        r = self.run_audit()
        self.assertEqual(r["gtfsStopsWithinRadius"], 0)
        self.assertEqual(r["autoVerifiedStopAnchors"], 0)


if __name__ == "__main__":
    unittest.main()
