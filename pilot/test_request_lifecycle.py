"""Synthetic cancellation race, isolation, capacity and generation checks."""
import unittest

from pilot.request_lifecycle import (
    TaskTicket, RemoteTaskRegistry, ClientGenerationGate,
    SharedFetchSubscriptions,
)


class Clock:
    def __init__(self):
        self.time = 100.0

    def __call__(self):
        return self.time


class RequestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server = RemoteTaskRegistry(
            max_active=2, max_records=3, clock=self.clock)
        self.ticket = self.make_ticket()

    def make_ticket(self, *, principal="A", session="sa",
                    task="task-1", generation=1, expiry=140.0):
        return TaskTicket(principal, session, task, generation,
                          "snapshot-signed-01", 99.0, expiry)

    def test_cancel_before_registration_creates_a_real_tombstone(self):
        self.assertEqual(self.server.cancel(self.ticket, "A"), "STOPPED")
        self.assertEqual(self.server.register(self.ticket, "A"),
                         "REJECTED_CANCELLED")
        self.assertEqual(self.server.state(self.ticket, "A"), "STOPPED")

    def test_running_cancellation_is_stopping_until_worker_acknowledges(self):
        self.assertEqual(self.server.register(self.ticket, "A"), "RUNNING")
        self.assertEqual(self.server.cancel(self.ticket, "A"), "STOPPING")
        self.assertTrue(self.server.should_stop(self.ticket, "A"))
        self.assertEqual(self.server.finish(self.ticket, "A"), "STOPPED")

    def test_cancel_is_idempotent(self):
        self.server.register(self.ticket, "A")
        self.assertEqual(self.server.cancel(self.ticket, "A"), "STOPPING")
        self.assertEqual(self.server.cancel(self.ticket, "A"), "STOPPING")
        self.assertEqual(self.server.finish(self.ticket, "A"), "STOPPED")
        self.assertEqual(self.server.cancel(self.ticket, "A"), "STOPPED")

    def test_completion_before_cancel_cannot_be_rewritten_as_kill(self):
        self.server.register(self.ticket, "A")
        self.assertEqual(self.server.finish(self.ticket, "A"), "COMPLETED")
        self.assertEqual(self.server.cancel(self.ticket, "A"), "COMPLETED")

    def test_wrong_owner_cannot_cancel_or_start_a_task(self):
        self.server.register(self.ticket, "A")
        with self.assertRaises(PermissionError):
            self.server.cancel(self.ticket, "B")
        with self.assertRaises(PermissionError):
            self.server.register(self.ticket, "B")
        self.assertFalse(self.server.should_stop(self.ticket, "A"))

    def test_session_and_generation_isolate_unrelated_tasks(self):
        other = self.make_ticket(principal="B", session="sb", task="task-1")
        self.server.register(self.ticket, "A")
        self.server.register(other, "B")
        self.server.cancel(self.ticket, "A")
        self.assertTrue(self.server.should_stop(self.ticket, "A"))
        self.assertFalse(self.server.should_stop(other, "B"))

    def test_duplicate_registration_never_launches_twice(self):
        self.assertEqual(self.server.register(self.ticket, "A"), "RUNNING")
        self.assertEqual(self.server.register(self.ticket, "A"),
                         "DUPLICATE_RUNNING")

    def test_mismatched_ticket_fields_cannot_reuse_identity(self):
        self.server.register(self.ticket, "A")
        altered = self.make_ticket(expiry=150.0)
        with self.assertRaises(ValueError):
            self.server.cancel(altered, "A")

    def test_concurrency_budget_denies_new_jobs_without_killing_existing(self):
        a = self.ticket
        b = self.make_ticket(task="two")
        c = self.make_ticket(task="three")
        self.server.register(a, "A")
        self.server.register(b, "A")
        self.assertEqual(self.server.register(c, "A"), "RATE_LIMITED")
        self.assertFalse(self.server.should_stop(a, "A"))
        self.assertFalse(self.server.should_stop(b, "A"))

    def test_saturated_tombstone_store_is_fail_closed(self):
        a = self.ticket
        b = self.make_ticket(task="two")
        c = self.make_ticket(task="three")
        d = self.make_ticket(task="four")
        for t in (a, b, c):
            self.assertEqual(self.server.cancel(t, "A"), "STOPPED")
        self.assertEqual(self.server.cancel(d, "A"),
                         "STOPPING_CAPACITY_BLOCK")
        self.assertEqual(self.server.register(d, "A"), "RATE_LIMITED")
        self.assertEqual(self.server.register(
            self.make_ticket(task="five"), "A"), "RATE_LIMITED")

    def test_lease_expiry_causes_cooperative_cancellation(self):
        self.server.register(self.ticket, "A")
        self.clock.time = 141.0
        self.assertTrue(self.server.should_stop(self.ticket, "A"))
        self.assertEqual(self.server.state(self.ticket, "A"), "STOPPING")
        self.assertEqual(self.server.finish(self.ticket, "A"), "STOPPED")

    def test_tombstone_can_expire_but_ticket_cannot_be_restarted(self):
        self.server.cancel(self.ticket, "A")
        self.clock.time = 155.0
        self.assertEqual(self.server.state(self.ticket, "A"), "UNKNOWN")
        self.assertEqual(self.server.register(self.ticket, "A"),
                         "REJECTED_EXPIRED")

    def test_invalid_ticket_and_non_authenticating_identity_are_rejected(self):
        with self.assertRaises(ValueError):
            self.make_ticket(expiry=99.0)
        with self.assertRaises(PermissionError):
            self.server.cancel(self.ticket, "ANOTHER_USER")


class ClientGateTests(unittest.TestCase):
    def setUp(self):
        self.client = ClientGenerationGate("A", "sa")
        self.a = TaskTicket("A", "sa", "one", 1, "s", 99.0, 140.0)
        self.b = TaskTicket("A", "sa", "two", 2, "s", 99.0, 140.0)

    def test_x_cancels_foreground_search_not_existing_guidance(self):
        self.client.commit_guidance("old-route")
        self.client.begin(self.a)
        self.assertEqual(self.client.cancel_foreground(), self.a)
        self.assertEqual(self.client.guidance_id, "old-route")
        self.assertFalse(self.client.accepts(self.a))

    def test_new_generation_rejects_late_prior_search_result(self):
        self.client.begin(self.a)
        self.client.begin(self.b)
        self.assertFalse(self.client.accepts(self.a))
        self.assertTrue(self.client.accepts(self.b))

    def test_generation_replay_is_rejected(self):
        self.client.begin(self.a)
        with self.assertRaises(ValueError):
            self.client.begin(self.a)

    def test_first_selection_is_immutable_under_later_enrichment(self):
        self.client.begin(self.a)
        self.assertTrue(self.client.select_itinerary(self.a, "route-1"))
        self.assertFalse(self.client.select_itinerary(self.a, "route-2"))
        self.assertFalse(self.client.accepts_enrichment(self.a, "route-2"))
        self.assertTrue(self.client.accepts_enrichment(self.a, "route-1"))

    def test_cross_session_ticket_rejected(self):
        bad = TaskTicket("B", "sb", "x", 1, "s", 99.0, 140.0)
        with self.assertRaises(PermissionError):
            self.client.begin(bad)


class SharedFetchTests(unittest.TestCase):
    def test_one_subscriber_cannot_cancel_another_fetch_subscriber(self):
        fetch = SharedFetchSubscriptions()
        a = TaskTicket("A", "sa", "one", 1, "s", 99.0, 140.0)
        b = TaskTicket("B", "sb", "two", 1, "s", 99.0, 140.0)
        fetch.attach("timetable-data", a)
        fetch.attach("timetable-data", b)
        self.assertFalse(fetch.detach("timetable-data", a))
        self.assertEqual(fetch.count("timetable-data"), 1)
        self.assertTrue(fetch.detach("timetable-data", b))
        self.assertEqual(fetch.count("timetable-data"), 0)

    def test_unknown_detach_does_not_kill_builder(self):
        fetch = SharedFetchSubscriptions()
        a = TaskTicket("A", "sa", "one", 1, "s", 99.0, 140.0)
        self.assertFalse(fetch.detach("unrelated", a))
