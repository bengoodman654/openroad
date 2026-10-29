import datetime as dt
import json
import sqlite3
import pathlib
import tempfile
import unittest
import zipfile

from maintenance.gtfs_refresh.build_sqlite import build_index
from maintenance.gtfs_refresh.compact_sqlite import compact_index
from maintenance.gtfs_refresh.query_sqlite import timetable_query

class CompactIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.zip=self.root/"source.zip"
        self.full=self.root/"full.sqlite"
        self.compact=self.root/"compact.sqlite"
        files={
          "agency.txt":"agency_id,agency_name,agency_url,agency_timezone\nA,A,https://example.org,Europe/London\n",
          "stops.txt":"stop_id,stop_name,stop_lat,stop_lon\n"+
            "".join(f"S{i},Stop {i},{51.4545+i*.00003},-2.5879\n" for i in range(120)),
          "routes.txt":"route_id,route_short_name\n"+
            "".join(f"R{i},Bus {i}\n" for i in range(15)),
          "trips.txt":"route_id,service_id,trip_id\n"+
            "".join(f"R{i%15},S,TRIP_LONG_TEXT_{i}\n" for i in range(90)),
          "stop_times.txt":"trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"+
            "".join(
               f"TRIP_LONG_TEXT_{i},09:00:00,09:00:00,S0,1,0,1\n"
               f"TRIP_LONG_TEXT_{i},09:30:00,09:30:00,S60,2,1,0\n"
               for i in range(90)),
          "calendar.txt":"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,1,1,20261001,20270101\n",
          "calendar_dates.txt":"service_id,date,exception_type\nS,20261105,2\n",
          "notes.txt":"x"*12000,
        }
        with zipfile.ZipFile(self.zip,"w") as z:
            for n,v in files.items():z.writestr(n,v)
        build_index(self.zip,"south_west",self.full,dt.date(2026,10,29))
    def tearDown(self):self.temp.cleanup()
    def test_exact_stop_times_and_no_navigation_capabilities(self):
        out=compact_index(self.full,self.compact)
        self.assertEqual(out["rows"],180)
        self.assertFalse(out["productionDeploymentApproved"])
        a=sqlite3.connect(self.full)
        b=sqlite3.connect(self.compact)
        self.assertEqual(
           a.execute("SELECT * FROM stop_times ORDER BY trip_id,seq").fetchall(),
           b.execute("SELECT * FROM stop_times ORDER BY trip_id,seq").fetchall())
        self.assertEqual(b.execute("PRAGMA quick_check").fetchone()[0],"ok")
        a.close();b.close()
    def test_existing_research_api_yields_same_scheduled_options(self):
        compact_index(self.full,self.compact)
        args=("south_west",(51.4545,-2.5879),(51.4563,-2.5879),
              dt.date(2026,10,29),8*3600+30*60)
        a=timetable_query(self.full,*args,walk_cap_m=110)
        b=timetable_query(self.compact,*args,walk_cap_m=110)
        self.assertEqual(a["outcome"],b["outcome"])
        self.assertEqual(a["results"],b["results"])
    def test_reject_overwrite(self):
        compact_index(self.full,self.compact)
        with self.assertRaises(ValueError):compact_index(self.full,self.compact)
