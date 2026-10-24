"""Synthetic reference-model checks only; 0 real acceptance integrations."""
import unittest
from datetime import datetime,timezone,timedelta
from reference import *

class ReferenceContracts(unittest.TestCase):
    def test_status_dimensions_and_envelope(self):
        v=dict(requestId="r",generation=1,operationId="o",taskType="JOURNEY",snapshotId="S",schemaVersion="2.2",outcome="NO_MATCH",reasonCode="KNOWN_ZERO",coverage={},provenance={},timeBasis="Europe/London",validUntil="2026-10-23T12:00:00+00:00",results=[],warnings=[],nextActions=[],realtimeStatus="UNAVAILABLE",serviceStatus="UNKNOWN",remoteJobStatus="RUNNING")
        self.assertTrue(envelope_ok(v))
        v["validUntil"]="2026-10-23T12:00:00";self.assertFalse(envelope_ok(v))
        v["validUntil"]="2026-10-23T12:00:00+00:00";v["outcome"]="UNAVAILABLE";self.assertFalse(envelope_ok(v))
    def test_explicit_city_beats_gps(self):
        self.assertEqual(location("Coventry",viewport="Bristol",gps="Bristol",opt_in=True),("explicit","Coventry"))
    def test_map_pin_beats_viewport(self):
        self.assertEqual(location(pin="Coventry",viewport="Bristol"),("pin","Coventry"))
    def test_gps_not_default(self):
        self.assertEqual(location(gps="Bristol"),("none",None))
    def test_same_number_different_operator(self):
        self.assertNotEqual(identity("A","line","75"),identity("B","line","75"))
    def test_missing_data_differs_from_no_service(self):
        self.assertEqual(outcome(False,False,False,False),"COVERAGE_MISSING")
        self.assertEqual(outcome(True,False,False,False),"NO_MATCH")
    def test_no_active_service_is_no_journey(self):
        self.assertEqual(outcome(True,True,False,False),"NO_JOURNEY")
    def test_hard_constraints_must_pass(self):
        j=dict(snapshot="S",calendar=True,complete=True,walk_ok=True,transfer_ok=True,cancelled=False,accessible=True)
        self.assertTrue(eligible(j,"S",True))
        for key in ("calendar","complete","walk_ok","transfer_ok"):
            self.assertFalse(eligible({**j,key:False},"S"))
    def test_unknown_accessibility_not_eligible(self):
        j=dict(snapshot="S",calendar=True,complete=True,walk_ok=True,transfer_ok=True,accessible=None)
        self.assertFalse(eligible(j,"S",True))
    def test_snapshot_pinning(self):
        j=dict(snapshot="S",calendar=True,complete=True,walk_ok=True,transfer_ok=True)
        self.assertFalse(eligible(j,"T"))
    def test_missing_realtime_keeps_schedule(self):
        self.assertTrue(service_selectable(True,False,False))
    def test_verified_cancelled_not_selectable(self):
        self.assertFalse(service_selectable(True,True,True))
    def test_stale_or_unmatched_not_fresh(self):
        self.assertEqual(live_state(450,True),"LAST_KNOWN")
        self.assertEqual(live_state(30,False),"LAST_KNOWN")
        self.assertEqual(live_state(2000,True),"UNAVAILABLE")
    def test_x_priority_foreground_over_guidance(self):
        self.assertEqual(x_action(foreground=True,guidance=True),"CANCEL_FOREGROUND")
        self.assertEqual(x_action(guidance=True),"CONFIRM_STOP_GUIDANCE")
    def test_x_idle_close_and_disabled(self):
        self.assertEqual(x_action(result=True),"CLOSE_RESULT")
        self.assertEqual(x_action(),"DISABLED")
    def test_dirty_edit_needs_confirmation(self):
        self.assertEqual(x_action(foreground=True,dirty=True),"CONFIRM_DISCARD")
    def test_reject_late_generation(self):
        t=Task("r","S",4);self.assertFalse(t.accept("r",3,"S"))
        t.cancel();self.assertFalse(t.accept("r",4,"S"))
    def test_reject_snapshot_mismatch(self):
        self.assertFalse(Task("r","S").accept("r",0,"T"))
    def test_cancel_before_job_admission(self):
        now=datetime(2026,10,22,tzinfo=timezone.utc);r=Registry()
        r.cancel("D","r",now)
        self.assertFalse(r.admit("D","r",now+timedelta(seconds=1)))
        self.assertTrue(r.admit("E","r",now+timedelta(seconds=1)))
    def test_shared_work_not_killed(self):
        s=Shared({"a","b"});s.detach("a")
        self.assertTrue(s.active);self.assertEqual(s.subscribers,{"b"})
    def test_scope_release_gate(self):
        self.assertFalse(release_gate({"C1","C2"},{"C1"},True,True,True))
        self.assertFalse(release_gate({"C1"},{"C1"},True,True,False))
        self.assertTrue(release_gate({"C1"},{"C1"},True,True,True))

if __name__=="__main__":unittest.main()
