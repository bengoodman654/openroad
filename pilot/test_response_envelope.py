"""Envelope oracles: no ghost journeys, no accidental release claims."""
import unittest
from datetime import date

from pilot.gtfs_engine import load_region
from pilot.test_gtfs_engine import make_feed
from pilot.journey_options import journey_options
from pilot.request_lifecycle import TaskTicket
from pilot.response_envelope import envelope


class EnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_region(make_feed(), "Coventry", "fixture",
                                   date(2026, 10, 26), sha256="fixture")
        cls.ticket = TaskTicket("A", "sa", "task", 7, "snapshot-A", 99, 140)

    def valid_result(self):
        return journey_options(
            self.snapshot, "A", "D", 7*3600+55*60)

    def make(self, result, status="COMPLETED"):
        return envelope(self.ticket, self.snapshot, result, status)

    def test_valid_scheduled_itinerary_remains_nonselectable(self):
        result = self.make(self.valid_result())
        self.assertEqual(result["outcome"], "OK")
        self.assertTrue(result["results"])
        self.assertFalse(result["results"][0]["selectable"])
        self.assertEqual(result["serviceStatus"], "SCHEDULED_UNVERIFIED")
        self.assertIn("departUTC", result["results"][0]["legs"][0])
        self.assertIsNone(result["validUntil"])

    def test_success_never_claims_live_vehicle_predictions(self):
        result = self.make(self.valid_result())
        self.assertEqual(result["realtimeStatus"], "SCHEDULED_ONLY")
        self.assertEqual(result["provenance"]["gtfsSHA256"], "fixture")

    def test_remote_stopping_supresses_precomputed_result(self):
        result = self.make(self.valid_result(), "STOPPING")
        self.assertEqual(result["outcome"], "CANCELLED")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["remoteJobStatus"], "STOPPING")

    def test_remote_stopped_suppresses_result(self):
        result = self.make(self.valid_result(), "STOPPED")
        self.assertEqual(result["outcome"], "CANCELLED")
        self.assertEqual(result["results"], [])

    def test_local_cancellation_does_not_claim_no_service(self):
        result = self.make({"outcome": "CANCELLED", "results": []})
        self.assertEqual(result["reasonCode"], "REQUEST_CANCELLED")
        self.assertNotEqual(result["outcome"], "NO_JOURNEY")

    def test_search_budget_is_not_no_service(self):
        result = self.make({"outcome": "SEARCH_LIMIT", "results": []})
        self.assertEqual(result["outcome"], "TIMEOUT")
        self.assertEqual(result["reasonCode"], "SEARCH_BUDGET_EXHAUSTED")

    def test_unverified_unknown_trip_identity_is_fail_closed(self):
        r = self.valid_result()
        r["results"][0]["legs"][0]["tripOccurrence"] = (
            "fixture:MISSING:2026-10-26")
        x = self.make(r)
        self.assertEqual(x["outcome"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(x["results"], [])

    def test_bus_leg_must_follow_real_contiguous_gtfs_events(self):
        r = self.valid_result()
        # Real T1 runs A -> B -> C only. Publishing A -> D as T1 is a lie.
        leg = r["results"][0]["legs"][0]
        leg["to"] = "D"
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")
        self.assertEqual(x["results"], [])

    def test_fake_boarding_time_is_rejected_even_on_real_trip(self):
        r = self.valid_result()
        r["results"][0]["legs"][0]["depart"] += 60
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_boarding_at_no_pickup_stop_rejected(self):
        r = self.valid_result()
        leg = r["results"][0]["legs"][0]
        # T1 serves B but cannot pick up there. Reuse the true trip identity.
        leg["from"] = "B"
        leg["depart"] = 8*3600 + 10*60
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_false_alighting_stop_is_rejected(self):
        r = self.valid_result()
        leg = r["results"][0]["legs"][0]
        # T1 drops off at C, not at the intermediate B.
        leg["to"] = "B"
        leg["arrive"] = 8*3600 + 10*60
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_line_mismatch_is_fail_closed(self):
        r = self.valid_result()
        r["results"][0]["legs"][0]["publicLine"] = "IMPOSTOR"
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_discontinuous_walking_bus_stages_are_fail_closed(self):
        r = self.valid_result()
        self.assertGreaterEqual(len(r["results"][0]["legs"]), 2)
        r["results"][0]["legs"][1]["from"] = "A"
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_unknown_engine_error_does_not_claim_no_coverage(self):
        x = self.make({"outcome": "UNEXPECTED", "results": []})
        self.assertEqual(x["outcome"], "PROVIDER_UNAVAILABLE")

    def test_no_journey_drops_injected_routes(self):
        r = {"outcome": "NO_JOURNEY", "results":
             self.valid_result()["results"]}
        x = self.make(r)
        self.assertEqual(x["outcome"], "NO_JOURNEY")
        self.assertEqual(x["results"], [])

    def test_missing_worker_ack_does_not_publish_routes(self):
        x = self.make(self.valid_result(), "RUNNING")
        self.assertEqual(x["reasonCode"], "WORKER_NOT_ACKNOWLEDGED")
        self.assertEqual(x["results"], [])

    def test_request_identity_and_service_time_are_explicit(self):
        x = self.make(self.valid_result())
        self.assertEqual(x["requestId"], "task")
        self.assertEqual(x["generation"], 7)
        self.assertEqual(x["snapshotId"], "snapshot-A")
        self.assertEqual(x["timeBasis"]["serviceDate"], "2026-10-26")
