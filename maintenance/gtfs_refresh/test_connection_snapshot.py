"""Full timetable connection-scan integration on a tiny synthetic index."""
import datetime as dt
import json
import sqlite3
import unittest

from maintenance.gtfs_refresh.connection_snapshot import (
    load_city_snapshot,CitySnapshotBudgetExceeded,CitySnapshotCancelled)
from maintenance.gtfs_refresh.test_query_sqlite import IndexRoutingTests
from pilot.journey_options import journey_options
from pilot.pedestrian_graph import PedestrianGraph
from pilot.transfer_connector_gate import (
    StopSideReview,independently_reviewed_links)


class CityConnectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=IndexRoutingTests("test_refuse_unsupported_date")
        self.fixture.setUp()
        self.db=self.fixture.db
        self.A=(51.4545,-2.5879)
        self.B=(51.46,-2.595)

    def tearDown(self):
        self.fixture.tearDown()

    def load(self, **kwargs):
        return load_city_snapshot(
            self.db,"south_west","Bristol",dt.date(2026,10,29),
            self.A,self.B,radius_m=700,**kwargs)

    def test_direct_trip_continuity_and_real_time(self):
        s=self.load()
        self.assertEqual(s.region,"south_west")
        self.assertGreater(s.active_service_count,0)
        self.assertIn("T0",s.trips)
        self.assertTrue(any(c.trip=="T0" and
            (c.a,c.b)==("A","B") for c in s.connections))
        p=journey_options(s,"A","B",8*3600+40*60)
        self.assertEqual(p["outcome"],"OK",p)
        self.assertEqual(p["results"][0]["arrival"],9*3600+20*60)

    def test_same_stop_buses_transfer_correctly(self):
        s=self.load()
        p=journey_options(s,"A","B",9*3600+60,max_transfers=2)
        self.assertEqual(p["outcome"],"OK",p)
        self.assertTrue(any(q["transfers"]==1 for q in p["results"]),p)

    def test_stops_not_connected_by_geographic_proximity(self):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO stops VALUES(?,?,?,?)",
                       ("Y","Y",51.4562,-2.5904))
            db.execute("UPDATE stop_times SET stop_id='Y' "
                       "WHERE trip_id='T2' AND seq=1")
        s=self.load()
        self.assertIn("Y",s.stops)
        no=journey_options(s,"A","B",9*3600+60)
        self.assertEqual(no["outcome"],"NO_JOURNEY",no)
        graph=PedestrianGraph("synthetic-osm")
        X=(s.stops["X"].lat,s.stops["X"].lon)
        Y=(s.stops["Y"].lat,s.stops["Y"].lon)
        graph.add_way("validated-footway",[("X",*X),("Y",*Y)],
                      {"highway":"footway"})
        reviews=[]
        for key,pt in (("X",X),("Y",Y)):
            reviews.append(StopSideReview(
                stop_id=key,osm_node_id=key,atco_code=key,
                reviewer="synthetic test reviewer",
                reviewed_on=dt.date(2026,10,29),
                method="ON_SITE_FIELD_CHECK",
                evidence_ref="SYNTHETIC-"+key,
                graph_sha256=graph.source_sha256,
                gtfs_sha256=s.source_sha256,
                stop_side="PAVEMENT_BY_STOP",
                crossing_checked=True,pavement_access_checked=True,
                to_graph=True,from_graph=True,
                geometry=(pt,pt),metres=0,seconds=0))
        evidence=independently_reviewed_links(
            graph,s,reviews,dt.date(2026,10,29))
        self.assertEqual(evidence["outcome"],"OK",evidence)
        yes=journey_options(
            s,"A","B",9*3600+60,footpaths=evidence["links"],
            max_transfers=2,max_walk_m=180)
        self.assertEqual(yes["outcome"],"OK",yes)
        self.assertTrue(any(q["transfers"]==1 and
            q["walkedMetres"]>0 for q in yes["results"]),yes)
        self.assertTrue(all("NO_ACCESSIBILITY_PROOF" in q["warnings"]
                            for q in yes["results"]))

    def test_outside_area_intermediate_stop_is_not_skipped(self):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO stops VALUES(?,?,?,?)",
                       ("OUT","outside",52.0,-2.0))
            db.execute("DELETE FROM stop_times WHERE trip_id='T4'")
            db.executemany("INSERT INTO stop_times VALUES(?,?,?,?,?,?,?)",[
                ("T4",1,"A",10*3600,10*3600,0,1),
                ("T4",2,"OUT",10*3600+300,10*3600+300,0,0),
                ("T4",3,"B",10*3600+600,10*3600+600,1,0)])
        s=self.load()
        self.assertFalse(any(c.trip=="T4" and c.a=="A" and c.b=="B"
                             for c in s.connections))

    def test_cancel_and_connection_budget_are_not_misreported_as_no_service(self):
        with self.assertRaises(CitySnapshotCancelled):
            self.load(cancel=lambda:True)
        with self.assertRaises(CitySnapshotBudgetExceeded):
            self.load(max_trips=1)

    def test_wrong_calendar_day_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"No source calendar"):
            load_city_snapshot(
                self.db,"south_west","Bristol",dt.date(2028,10,29),
                self.A,self.B,radius_m=700)

    def test_sqlite_source_hash_matches_connection_snapshot(self):
        snap=self.load()
        with sqlite3.connect(self.db) as db:
            raw=db.execute(
                "SELECT value FROM info WHERE name='sourceArchiveSha256'"
            ).fetchone()[0]
        self.assertEqual(snap.source_sha256,json.loads(raw))

if __name__=="__main__":
    unittest.main()
