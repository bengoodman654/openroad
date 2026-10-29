import datetime as dt
import pathlib
import tempfile
import unittest
import zipfile
from maintenance.gtfs_refresh.build_sqlite import build_index
from maintenance.gtfs_refresh.query_sqlite import timetable_query, SearchCancelled

class IndexRoutingTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.t.name)
        self.z=self.root/"f.zip";self.db=self.root/"i.sqlite"
        stops="stop_id,stop_name,stop_lat,stop_lon\n"
        for name,lat,lon in [("A",51.4545,-2.5879),
                             ("X",51.456,-2.590),
                             ("B",51.46,-2.595)]:
            stops+=f"{name},{name},{lat},{lon}\n"
        for i in range(110):
            stops+=f"P{i},P{i},{51.4545+i*0.000001},-2.5879\n"
        data={
          "agency.txt":"agency_id,agency_name,agency_url,agency_timezone\nA,Test,https://example.org,Europe/London\n",
          "routes.txt":"route_id,route_short_name\n"+ "".join(f"R{i},Line {i}\n" for i in range(12)),
          "trips.txt":"route_id,service_id,trip_id\n"+
                      "".join(f"R{i%12},S,T{i}\n" for i in range(60)),
          "stops.txt":stops,
          "stop_times.txt":"trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"+
            "T0,09:00:00,09:00:00,A,1,0,1\nT0,09:20:00,09:20:00,B,2,1,0\n"+
            "T1,09:05:00,09:05:00,A,1,0,1\nT1,09:10:00,09:10:00,X,2,1,0\n"+
            "T2,09:15:00,09:15:00,X,1,0,1\nT2,09:30:00,09:30:00,B,2,1,0\n"+
            "T3,24:05:00,24:05:00,A,1,0,1\nT3,24:45:00,24:45:00,B,2,1,0\n"+
            "".join(f"T{i},12:00:00,12:00:00,P0,1,0,0\n" for i in range(4,60)),
          "calendar.txt":"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,1,1,20261001,20270201\n",
          "calendar_dates.txt":"service_id,date,exception_type\nS,20261101,1\n",
          "notes.txt":"x"*12000,
        }
        with zipfile.ZipFile(self.z,"w") as z:
            for n,c in data.items():z.writestr(n,c)
        build_index(self.z,"south_west",self.db,dt.date(2026,10,29))
    def tearDown(self):self.t.cleanup()
    def test_scheduled_direct_and_alternative_nonselectable(self):
        a=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2026,10,29),8*3600+40*60,walk_cap_m=180)
        self.assertEqual(a["outcome"],"OK")
        self.assertTrue(a["results"])
        self.assertEqual(a["results"][0]["trips"],["T0"])
        self.assertFalse(a["results"][0]["selectable"])
        self.assertFalse(a["results"][0]["walkGeometryVerified"])
        for journey in a["results"]:
            self.assertGreaterEqual(journey["accessWalkMetresLowerBound"],0)
            self.assertGreaterEqual(journey["egressWalkMetresLowerBound"],0)
            self.assertFalse(journey["accessibilityVerified"])
    def test_transfer_when_direct_removed_or_departing_late(self):
        a=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2026,10,29),9*3600+1*60,walk_cap_m=180)
        self.assertEqual(a["outcome"],"OK")
        self.assertTrue(any(len(x["trips"])==2 for x in a["results"]))
    def test_after_midnight_service_can_use_previous_calendar_day(self):
        results=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2026,10,29),5*60,
            walk_cap_m=180)
        self.assertEqual(results["outcome"],"OK")
        self.assertEqual(results["results"][0]["trips"],["T3"])
        self.assertEqual(results["results"][0]["departureSec"],5*60)
        self.assertFalse(results["results"][0]["selectable"])

    def test_dense_early_stop_arrivals_do_not_starve_transfer(self):
        # More than 600 early, irrelevant stop arrivals used to crowd out
        # the real T1 -> T2 connection when search sorted first legs and
        # arbitrarily kept only the first 600.
        import sqlite3
        with sqlite3.connect(self.db) as db:
            for n in range(15):
                trip=f"DENSE{n:02d}"
                db.execute(
                    "INSERT INTO trips(trip_id,route_id,service_id,headsign,shape_id) "
                    "VALUES(?,?,?,?,?)",(trip,"R0","S","Other",""))
                calls=[(trip,1,"A",9*3600+2*60,9*3600+2*60,0,1)]
                for ix in range(60):
                    secs=9*3600+2*60+(ix+1)*3
                    calls.append((trip,ix+2,f"P{ix}",secs,secs,0,0))
                db.executemany("INSERT INTO stop_times VALUES(?,?,?,?,?,?,?)",calls)
        out=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2026,10,29),
            9*3600+60,walk_cap_m=180,budget_secs=4)
        self.assertEqual(out["outcome"],"OK")
        self.assertTrue(any(r["trips"]==["T1","T2"] for r in out["results"]))
        self.assertTrue(all(not r["selectable"] for r in out["results"]))

    def prepare_field_reviewed_transfer(self, one_way=False):
        """Fixture-only field review: no real-world stop access is asserted."""
        import json,sqlite3
        from types import SimpleNamespace
        from pilot.gtfs_engine import Stop
        from pilot.pedestrian_graph import PedestrianGraph
        from pilot.transfer_connector_gate import (
            StopSideReview,independently_reviewed_links)
        X=(51.456,-2.590)
        Y=(51.4562,-2.5904)
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO stops VALUES(?,?,?,?)",
                       ("Y","Y",*Y))
            db.execute("UPDATE stop_times SET stop_id='Y' "
                       "WHERE trip_id='T2' AND seq=1")
            digest=json.loads(db.execute(
                "SELECT value FROM info WHERE name='sourceArchiveSha256'"
            ).fetchone()[0])
        graph=PedestrianGraph("fixture-osm-graph")
        graph.add_way("actual-mapped-footway",[
            ("X",*X),("Y",*Y)],
            {"highway":"footway",
             **({"oneway:foot":"yes"} if one_way else {})})
        snapshot=SimpleNamespace(
            source_sha256=digest,
            stops={"X":Stop("X","X",*X),
                   "Y":Stop("Y","Y",*Y)})
        reviews=[]
        for key,pt in [("X",X),("Y",Y)]:
            reviews.append(StopSideReview(
                stop_id=key,osm_node_id=key,atco_code=key,
                reviewer="synthetic test observer",
                reviewed_on=dt.date(2026,10,29),
                method="ON_SITE_FIELD_CHECK",
                evidence_ref="SYNTHETIC-FIXTURE-"+key,
                graph_sha256=graph.source_sha256,
                gtfs_sha256=digest,
                stop_side="PAVEMENT_BY_STOP",
                crossing_checked=True,pavement_access_checked=True,
                to_graph=True,from_graph=True,
                geometry=(pt,pt),metres=0,seconds=0))
        evidence=independently_reviewed_links(
            graph,snapshot,reviews,dt.date(2026,10,29),
            max_walk_m=180)
        self.assertEqual(evidence["outcome"],"OK",evidence)
        return evidence

    def transfer_query(self, evidence=None, cap=180, cancelled=lambda:False):
        return timetable_query(
            self.db,"south_west",(51.4545,-2.5879),(51.46,-2.595),
            dt.date(2026,10,29),9*3600+60,
            walk_cap_m=cap,budget_secs=4,
            verified_transfers=evidence,cancel=cancelled)

    def test_distinct_interchange_stops_are_not_automatically_joined(self):
        self.prepare_field_reviewed_transfer()
        result=self.transfer_query()
        self.assertEqual(result["outcome"],"NO_JOURNEY",result)

    def test_independent_osm_stop_side_review_unlocks_research_transfer(self):
        evidence=self.prepare_field_reviewed_transfer()
        result=self.transfer_query(evidence)
        self.assertEqual(result["outcome"],"OK",result)
        picked=[x for x in result["results"] if x["trips"]==["T1","T2"]]
        self.assertTrue(picked,result)
        option=picked[0]
        self.assertEqual(option["boarding"],["A","Y"])
        self.assertEqual(option["alighting"],["X","B"])
        self.assertTrue(option["transferGeometryVerified"])
        self.assertGreater(option["transferWalkMetres"],0)
        self.assertGreater(len(option["transferWalkGeometry"]),1)
        self.assertFalse(option["walkGeometryVerified"])
        self.assertFalse(option["selectable"])
        self.assertLessEqual(
            option["accessWalkMetresLowerBound"]+
            option["transferWalkMetres"]+
            option["egressWalkMetresLowerBound"],180)

    def test_explicit_field_review_bundle_must_match_exact_gtfs_source(self):
        evidence=self.prepare_field_reviewed_transfer()
        evidence={**evidence,"gtfsSourceSha256":"0"*64}
        with self.assertRaisesRegex(ValueError,"different GTFS"):
            self.transfer_query(evidence)

    def test_walking_allowance_excludes_even_verified_overlong_transfer(self):
        evidence=self.prepare_field_reviewed_transfer()
        self.assertEqual(self.transfer_query(evidence,cap=20)["outcome"],
                         "NO_JOURNEY")

    def test_corrupted_reviewed_path_cannot_be_used(self):
        from dataclasses import replace
        evidence=self.prepare_field_reviewed_transfer()
        bad=replace(evidence["links"][0],
                    geometry=((0.0,0.0),(0.0,0.0)))
        with self.assertRaisesRegex(ValueError,"does not meet"):
            self.transfer_query({**evidence,"links":[bad]+evidence["links"][1:]})

    def test_directional_foot_access_fails_closed(self):
        evidence=self.prepare_field_reviewed_transfer(one_way=True)
        self.assertEqual(len(evidence["links"]),1)
        self.assertEqual((evidence["links"][0].a,
                          evidence["links"][0].b),("X","Y"))
        self.assertEqual(self.transfer_query(evidence)["outcome"],"OK")

    def test_cancelled_reviewed_connection_query_cannot_return_late_route(self):
        evidence=self.prepare_field_reviewed_transfer()
        with self.assertRaises(SearchCancelled):
            self.transfer_query(evidence,cancelled=lambda:True)

    def test_cancellation_propagated(self):
        with self.assertRaises(SearchCancelled):
            timetable_query(self.db,"south_west",(51.4545,-2.5879),
                (51.46,-2.595),dt.date(2026,10,29),9*3600,
                cancel=lambda:True)
    def test_zero_budget_cannot_claim_no_journey(self):
        from maintenance.gtfs_refresh.query_sqlite import SearchBudget
        with self.assertRaises(SearchBudget):
            timetable_query(self.db,"south_west",(51.4545,-2.5879),
                (51.46,-2.595),dt.date(2026,10,29),
                9*3600,budget_secs=0)

    def test_timeout_and_cancellation_do_not_corrupt_index(self):
        from maintenance.gtfs_refresh.query_sqlite import SearchBudget
        with self.assertRaises(SearchBudget):
            timetable_query(self.db,"south_west",(51.4545,-2.5879),
                (51.46,-2.595),dt.date(2026,10,29),
                9*3600,budget_secs=-1)
        # The same immutable index remains usable after query interruption.
        good=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2026,10,29),
            9*3600,budget_secs=4)
        self.assertEqual(good["outcome"],"OK")

    def test_refuse_unsupported_date(self):
        a=timetable_query(self.db,"south_west",(51.4545,-2.5879),
            (51.46,-2.595),dt.date(2028,10,29),9*3600)
        self.assertEqual(a["outcome"],"CALENDAR_MISSING")
