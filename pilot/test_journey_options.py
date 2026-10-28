"""Isolated regression checks for walking transfers and alternative journeys."""
import unittest
from datetime import date
from pilot.gtfs_engine import load_region
from pilot.journey_options import Footpath, journey_options
from pilot.test_gtfs_engine import make_feed

class OptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=load_region(make_feed(),"Coventry","fixture",date(2026,10,26),sha256="fixture")

    def test_direct_bus(self):
        r=journey_options(self.snapshot,"A","B",7*3600+55*60)
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["results"][0]["arrival"],8*3600+10*60)
        self.assertEqual(r["results"][0]["transfers"],0)

    def test_transfer_without_footpaths(self):
        r=journey_options(self.snapshot,"A","D",7*3600+55*60)
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["results"][0]["arrival"],8*3600+33*60)
        self.assertEqual(r["results"][0]["transfers"],1)
        self.assertNotIn("T4",repr(r["results"][0]["legs"]))

    def test_explicit_footpath_transfer(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["results"][0]["arrival"],8*3600+32*60, repr(r))
        self.assertIn("UNVERIFIED_WALK_GEOMETRY",r["results"][0]["warnings"], repr(r))
        self.assertEqual(r["results"][0]["walkedMetres"],120, repr(r))

    def test_footpath_outcome_only(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertEqual(r["outcome"],"OK")

    def test_footpath_arrival_only(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertEqual(r["results"][0]["arrival"],8*3600+32*60)

    def test_footpath_warning_only(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertIn("UNVERIFIED_WALK_GEOMETRY",r["results"][0]["warnings"])

    def test_footpath_metres_only(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertEqual(r["results"][0]["walkedMetres"],120)

    def test_hard_walk_limit(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120)],max_walk_m=100)
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_invalid_footpath_rejected(self):
        with self.assertRaises(ValueError):
            journey_options(self.snapshot,"A","D",0,
                footpaths=[Footpath("B","C",-1,100)])

    def test_unknown_stop(self):
        self.assertEqual(journey_options(self.snapshot,"UNKNOWN","D",0)["outcome"],
                         "COVERAGE_MISSING")

    def test_zero_transfers_means_one_bus(self):
        r=journey_options(self.snapshot,"A","D",7*3600+55*60,max_transfers=0)
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_a_budget_failure_is_not_no_service(self):
        r=journey_options(self.snapshot,"A","D",7*3600+55*60,max_labels=1)
        self.assertEqual(r["outcome"],"SEARCH_LIMIT")

    def test_transfer_buffer_can_be_configured(self):
        default=journey_options(self.snapshot,"A","D",7*3600+55*60)
        self.assertEqual(default["results"][0]["arrival"],8*3600+33*60)
        zero=journey_options(self.snapshot,"A","D",7*3600+55*60,
                             transfer_seconds=0)
        self.assertEqual(zero["results"][0]["arrival"],8*3600+32*60)

    def test_transfer_limit_cannot_be_bypassed_by_boarding_same_trip(self):
        result=journey_options(self.snapshot,"A","D",7*3600+55*60,
                               max_transfers=0)
        self.assertEqual(result["outcome"],"NO_JOURNEY")

    def test_explicit_footpath_geometry_is_not_accessibility_proof(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
                          footpaths=[Footpath("B","C",120,120,True,
                              ((52.4090,-1.5106),(52.4100,-1.5106)),
                              "fixture","synthetic")])
        self.assertEqual(r["outcome"],"OK")
        self.assertIn("NO_ACCESSIBILITY_PROOF",r["results"][0]["warnings"])
        self.assertNotIn("UNVERIFIED_WALK_GEOMETRY",r["results"][0]["warnings"])

    def test_different_transfer_tradeoffs_are_both_returned(self):
        from pilot.gtfs_engine import Connection
        s=self.snapshot
        original=list(s.connections)
        s.routes["RD"]=("Direct","OP_A")
        s.trips["DIRECT"]=("RD","WEEK")
        s.connections=sorted(original+[Connection(
            "DIRECT","A","D",8*3600,8*3600+45*60,
            True,True,1,2)],key=lambda c:(c.depart,c.arrive,c.trip,c.a,c.b))
        try:
            r=journey_options(s,"A","D",7*3600+55*60)
        finally:
            s.connections=original
            del s.routes["RD"]
            del s.trips["DIRECT"]
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual([(x["arrival"],x["transfers"]) for x in r["results"]],
                         [(8*3600+33*60,1),(8*3600+45*60,0)])

    def test_clipped_loop_cannot_continue_through_missing_section(self):
        from pilot.gtfs_engine import Connection
        s=self.snapshot
        original=s.connections
        s.connections=[
            Connection("T1","A","B",8*3600,8*3600+5*60,
                       True,True,1,2),
            Connection("T1","B","D",8*3600+20*60,8*3600+25*60,
                       False,True,4,5),
        ]
        try:
            r=journey_options(s,"A","D",7*3600+55*60)
        finally:
            s.connections=original
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_many_stops_do_not_expand_into_all_pairs(self):
        from pilot.gtfs_engine import Stop, Connection, Snapshot
        from datetime import date
        s=self.snapshot
        from dataclasses import replace
        stops={f"S{i}":Stop(f"S{i}",f"Stop {i}",52.4081,-1.5106)
               for i in range(301)}
        connections=[Connection("LONG",f"S{i}",f"S{i+1}",
                        10*3600+i*60,10*3600+(i+1)*60,
                        True,True,i+1,i+2) for i in range(300)]
        x=replace(s, stops=stops, routes={"RL":("Long","OP_A")},
                  trips={"LONG":("RL","WEEK")}, connections=connections)
        r=journey_options(x,"S0","S300",10*3600,max_horizon_sec=20000)
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["results"][0]["arrival"],10*3600+300*60)
        self.assertEqual(r["results"][0]["transfers"],0)
        self.assertLess(r["expandedLabels"],1000)
        self.assertEqual(len(r["results"][0]["legs"]),1)

    def test_no_footpath_can_be_inferred_from_proximity(self):
        # B and C are physically close but cannot be walked between unless
        # an explicit directional footpath is supplied.
        from pilot.gtfs_engine import Connection
        s=self.snapshot
        original=s.connections
        s.connections=[c for c in original if c.trip in ("T3","T4")]
        try:
            r=journey_options(s,"B","D",8*3600+10*60)
        finally:
            s.connections=original
        self.assertEqual(r["outcome"],"NO_JOURNEY")


    def test_unverified_walk_with_nan_geometry_rejected(self):
        from math import nan
        p = Footpath("B", "C", 120, 120, False,
                     ((52.409, -1.5106), (nan, -1.5106)))
        with self.assertRaisesRegex(ValueError, "coordinates"):
            journey_options(self.snapshot, "B", "C", 8*3600, footpaths=[p])

    def test_unverified_walk_wrong_endpoint_rejected(self):
        p = Footpath("B", "C", 120, 120, False,
                     ((52.409, -1.5106), (52.409, -1.5106)))
        with self.assertRaisesRegex(ValueError, "does not reach"):
            journey_options(self.snapshot, "B", "C", 8*3600, footpaths=[p])

    def test_unverified_walk_wrong_geometry_length_rejected(self):
        p = Footpath("B", "C", 7, 120, False,
                     ((52.409, -1.5106), (52.410, -1.5106)))
        with self.assertRaisesRegex(ValueError, "disagrees with distance"):
            journey_options(self.snapshot, "B", "C", 8*3600, footpaths=[p])

    def test_malformed_walk_coordinate_pair_rejected(self):
        p = Footpath("B", "C", 120, 120, False,
                     ((52.409, -1.5106), (0,)))
        with self.assertRaisesRegex(ValueError, "Invalid footpath geometry"):
            journey_options(self.snapshot, "B", "C", 8*3600, footpaths=[p])

    def test_zero_duration_walk_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid footpath"):
            journey_options(self.snapshot, "B", "C", 8*3600,
                            footpaths=[Footpath("B", "C", 120, 0)])


    def test_cancelled_before_search_returns_no_journey_payload(self):
        result = journey_options(self.snapshot, "A", "D", 7*3600+55*60,
                                 cancel_check=lambda: True)
        self.assertEqual(result["outcome"], "CANCELLED")
        self.assertEqual(result["reasonCode"], "REQUEST_CANCELLED")
        self.assertEqual(result["results"], [])

    def test_cancellation_during_scanning_never_returns_partials(self):
        calls = [0]
        def cancel():
            calls[0] += 1
            return calls[0] >= 2
        result = journey_options(self.snapshot, "A", "D", 7*3600+55*60,
                                 cancel_check=cancel)
        self.assertEqual(result["outcome"], "CANCELLED")
        self.assertEqual(result["results"], [])
        self.assertGreaterEqual(calls[0], 2)

    def test_cancellation_hook_must_be_callable(self):
        with self.assertRaises(ValueError):
            journey_options(self.snapshot, "A", "D", 7*3600,
                            cancel_check="not-a-callback")

    def test_normal_search_still_succeeds_with_live_hook(self):
        result = journey_options(self.snapshot, "A", "D", 7*3600+55*60,
                                 cancel_check=lambda: False)
        self.assertEqual(result["outcome"], "OK")

if __name__=="__main__":
    unittest.main()
