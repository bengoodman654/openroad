"""Oracle tests for pinned physical journeys and alternative valid interchanges."""
import unittest

from pilot.verify_real import matches_pinned_multicriteria_option


class PinnedMultiOptionTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "expectedArrival": 45180,
            "expectedLines": ["24", "43"],
            "expectedTrips": ["TRIP24", "TRIP43"],
        }
        self.option = {
            "arrival": 45180,
            "legs": [
                {"mode": "BUS", "publicLine": "24",
                 "tripOccurrence": "south_west:TRIP24:2026-10-26",
                 "from": "ORIGIN", "to": "NEW_TRANSFER",
                 "depart": 43560, "arrive": 44220},
                {"mode": "BUS", "publicLine": "43",
                 "tripOccurrence": "south_west:TRIP43:2026-10-26",
                 "from": "NEW_TRANSFER", "to": "END",
                 "depart": 44580, "arrive": 45180},
            ],
        }

    def test_alternate_transfer_with_same_physical_trips_is_valid(self):
        self.assertTrue(matches_pinned_multicriteria_option(
            self.case, self.option))

    def test_wrong_vehicle_trip_identity_fails_even_if_arrival_equal(self):
        self.option["legs"][1]["tripOccurrence"] = (
            "south_west:ANOTHER_TRIP:2026-10-26")
        self.assertFalse(matches_pinned_multicriteria_option(
            self.case, self.option))

    def test_insufficient_interchange_time_fails(self):
        self.option["legs"][1]["depart"] = 44260
        self.assertFalse(matches_pinned_multicriteria_option(
            self.case, self.option))

    def test_different_interchange_stop_without_walk_fails(self):
        self.option["legs"][1]["from"] = "UNRELATED_STOP"
        self.assertFalse(matches_pinned_multicriteria_option(
            self.case, self.option))

    def test_wrong_line_or_arrival_fails(self):
        self.option["arrival"] = 45179
        self.assertFalse(matches_pinned_multicriteria_option(
            self.case, self.option))
        self.option["arrival"] = 45180
        self.option["legs"][0]["publicLine"] = "99"
        self.assertFalse(matches_pinned_multicriteria_option(
            self.case, self.option))


if __name__ == "__main__":
    unittest.main()
