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
