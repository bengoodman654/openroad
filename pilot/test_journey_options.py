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
        self.assertEqual(r["results"][0]["arrival"],8*3600+32*60)
        self.assertEqual(r["results"][0]["transfers"],1)

    def test_explicit_footpath_transfer(self):
        r=journey_options(self.snapshot,"B","D",8*3600+10*60,
            footpaths=[Footpath("B","C",120,120,False)])
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["results"][0]["arrival"],8*3600+32*60, repr(r))
        self.assertIn("UNVERIFIED_WALK_GEOMETRY",r["results"][0]["warnings"], repr(r))
        self.assertEqual(r["results"][0]["walkedMetres"],120, repr(r))

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

if __name__=="__main__":
    unittest.main()
