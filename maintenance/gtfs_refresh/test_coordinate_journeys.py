import datetime as dt
import unittest
from maintenance.gtfs_refresh.test_query_sqlite import IndexRoutingTests
from maintenance.gtfs_refresh.connection_snapshot import load_city_snapshot
from maintenance.gtfs_refresh.coordinate_journeys import coordinate_journeys


class CoordinateJourneysTests(unittest.TestCase):
    def setUp(self):
        self.fixture=IndexRoutingTests("test_refuse_unsupported_date")
        self.fixture.setUp()
        self.start=(51.4545,-2.5879)
        self.end=(51.46,-2.595)
        self.snapshot=load_city_snapshot(
            self.fixture.db,"south_west","Bristol",dt.date(2026,10,29),
            self.start,self.end,radius_m=700)

    def tearDown(self):
        self.fixture.tearDown()

    def query(self,when=8*3600+40*60,**kwargs):
        return coordinate_journeys(
            self.snapshot,self.start,self.end,when,max_walk_m=180,
            **kwargs)

    def test_provisional_coordinate_ride_is_not_selectable(self):
        result=self.query()
        self.assertEqual(result["outcome"],"OK",result)
        self.assertTrue(result["results"])
        first=result["results"][0]
        self.assertEqual(first["busLegs"][0]["tripOccurrence"].split(":")[1],
                         "T0")
        self.assertEqual(first["arrivalLowerBoundSec"],9*3600+20*60)
        self.assertFalse(first["selectable"])
        self.assertFalse(first["accessWalkGeometryVerified"])
        self.assertFalse(first["egressWalkGeometryVerified"])
        self.assertFalse(first["accessibilityVerified"])
        self.assertIn("UNVERIFIED_ORIGIN_DESTINATION_PEDESTRIAN_ACCESS",
                      first["warnings"])

    def test_after_direct_departure_one_change_bus_route_is_found(self):
        result=self.query(when=9*3600+60)
        self.assertEqual(result["outcome"],"OK",result)
        self.assertTrue(any(x["changes"]==1 for x in result["results"]),result)

    def test_source_pinned_stable_route_identity(self):
        r1=self.query()
        r2=self.query()
        self.assertEqual([r["clearRouteId"] for r in r1["results"]],
                         [r["clearRouteId"] for r in r2["results"]])
        self.assertTrue(all(len(r["clearRouteId"])==20 for r in r1["results"]))

    def test_cancellation_never_returns_route(self):
        result=self.query(cancel=lambda:True)
        self.assertEqual(result["outcome"],"CANCELLED")
        self.assertFalse(result["results"])

    def test_missing_coverage_is_honest(self):
        result=coordinate_journeys(self.snapshot,(54.0,-2.0),self.end,
                                   9*3600,max_walk_m=180)
        self.assertEqual(result["outcome"],"COVERAGE_MISSING")

    def test_arbitrary_pedestrian_geometry_is_rejected(self):
        bundle={"outcome":"OK","researchOnly":True,"selectable":False,
                "gtfsSourceSha256":"not-this-gtfs-snapshot",
                "graphSourceSha256":"untrusted",
                "links":[]}
        with self.assertRaises(ValueError):
            self.query(transfer_bundle=bundle)

    def test_shortlisted_stops_are_incomplete_not_a_claim_of_no_service(self):
        # This fixture has 110 extra nearby stops with no useful evening
        # buses. Searching only one never proves the city has no service.
        outcome=self.query(when=20*3600,max_nearby=1,max_pairs=1)
        self.assertEqual(outcome["outcome"],"SEARCH_LIMIT",outcome)
        self.assertFalse(outcome["results"])
        self.assertTrue(outcome["incompleteSearch"])

    def test_deadline_does_not_turn_into_false_no_journey(self):
        outcome=self.query(budget_s=0.000001)
        self.assertEqual(outcome["outcome"],"SEARCH_LIMIT",outcome)

    def test_user_walk_limit_is_not_silently_expanded(self):
        p=coordinate_journeys(
            self.snapshot,self.start,self.end,
            9*3600+60,max_walk_m=50)
        self.assertTrue(all(x["walkingDistanceMetresLowerBound"]<=50
                            for x in p["results"]))
        self.assertTrue(all(not x["selectable"] for x in p["results"]))

if __name__=="__main__":
    unittest.main()
