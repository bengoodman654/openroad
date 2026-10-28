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

    def test_stable_id_is_present_on_every_result(self):
        x = self.make(self.valid_result())
        self.assertTrue(all(row["id"].startswith("ptv2-")
                            for row in x["results"]))

    def test_late_enrichment_cannot_change_scheduled_itinerary_id(self):
        from copy import deepcopy
        from pilot.response_envelope import _stable_itinerary_id
        r = self.valid_result()["results"][0]
        changed = deepcopy(r)
        changed["legs"][0]["geometry"] = [[52.408, -1.510], [52.409, -1.510]]
        changed["legs"][0]["realtimePrediction"] = 999999
        self.assertEqual(_stable_itinerary_id(self.snapshot, r),
                         _stable_itinerary_id(self.snapshot, changed))

    def test_different_physical_trip_identity_changes_id(self):
        from copy import deepcopy
        from pilot.response_envelope import _stable_itinerary_id
        r = self.valid_result()["results"][0]
        changed = deepcopy(r)
        changed["legs"][0]["tripOccurrence"] = "fixture:DIFFERENT:2026-10-26"
        self.assertNotEqual(_stable_itinerary_id(self.snapshot, r),
                            _stable_itinerary_id(self.snapshot, changed))

    def test_client_generation_not_part_of_itinerary_identity(self):
        x = self.make(self.valid_result())
        next_ticket = TaskTicket("A", "sa", "task-next", 8, "snapshot-A", 99, 140)
        y = envelope(next_ticket, self.snapshot, self.valid_result())
        self.assertEqual([i["id"] for i in x["results"]],
                         [i["id"] for i in y["results"]])

    def test_duplicate_physical_journeys_collapse_to_one_id(self):
        from copy import deepcopy
        r = self.valid_result()
        r["results"] = [deepcopy(r["results"][0]),
                        deepcopy(r["results"][0])]
        x = self.make(r)
        self.assertEqual(x["outcome"], "OK")
        self.assertEqual(len(x["results"]), 1)

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

    def test_more_than_three_results_is_fail_closed_and_not_indexed(self):
        r = self.valid_result()
        r["results"] = r["results"] * 4
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")
        self.assertEqual(x["results"], [])

    def test_excessively_long_itinerary_is_fail_closed(self):
        r = self.valid_result()
        r["results"][0]["legs"] *= 17
        x = self.make(r)
        self.assertEqual(x["reasonCode"], "INVALID_PLANNER_OUTPUT")

    def test_source_validation_indexes_only_used_trips(self):
        from pilot.response_envelope import _segments_by_trip
        r = self.valid_result()
        indexed = _segments_by_trip(self.snapshot, r["results"])
        used = set()
        for opt in r["results"]:
            for leg in opt["legs"]:
                if leg["mode"] == "BUS":
                    used.add(leg["tripOccurrence"].split(":")[1])
        self.assertEqual(set(indexed), used)
        self.assertLessEqual(sum(len(v) for v in indexed.values()),
                             len(self.snapshot.connections))

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
