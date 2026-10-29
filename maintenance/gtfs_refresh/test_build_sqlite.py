import datetime as dt
import pathlib
import sqlite3
import tempfile
import unittest
import zipfile
from maintenance.gtfs_refresh.build_sqlite import build_index,FeedRejected,duration_seconds

class SQLiteIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name)
        self.source=self.root/"source.zip"
        self.out=self.root/"region.sqlite"
        self.today=dt.date(2026,10,29)
        content={
            "agency.txt":"agency_id,agency_name,agency_url,agency_timezone\nA,Test,https://example.org,Europe/London\n",
            "routes.txt":"route_id,route_short_name\n"+ "".join(f"R{i},B{i}\n" for i in range(15)),
            "trips.txt":"route_id,service_id,trip_id,trip_headsign\n"+
                        "".join(f"R{i%15},S,T{i},Clifton\n" for i in range(80)),
            "stops.txt":"stop_id,stop_name,stop_lat,stop_lon\n"+
                        "".join(f"{i},Stop {i},{51.4545+i*0.00001},-2.5879\n" for i in range(120)),
            "stop_times.txt":"trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"+
                        "".join(f"T{i},09:00:00,09:00:00,0,1,0,1\nT{i},09:35:00,09:35:00,1,2,1,0\n" for i in range(80)),
            "calendar.txt":"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"+
                           "S,1,1,1,1,1,1,1,20261001,20270201\n",
            "calendar_dates.txt":"service_id,date,exception_type\nS,20261102,2\n",
        }
        with zipfile.ZipFile(self.source,"w") as z:
            for name,data in content.items():z.writestr(name,data)
            z.writestr("notes.txt","x"*12000)
    def tearDown(self):self.tmp.cleanup()
    def test_bounded_index_build_and_source_pinned_metadata(self):
        record=build_index(self.source,"south_west",self.out,self.today)
        self.assertEqual(record["stopTimeCount"],160)
        self.assertFalse(record["eligibleForProductionPublication"])
        db=sqlite3.connect(self.out)
        self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0],"ok")
        self.assertEqual(db.execute(
            "SELECT count(*) FROM stop_times WHERE stop_id='0' AND departure_sec=32400").fetchone()[0],80)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM service_days WHERE date='2026-11-02'").fetchone()[0],0)
        self.assertEqual(db.execute(
            "SELECT pickup,dropoff FROM stop_times WHERE trip_id='T0' AND seq=1").fetchone(),(0,1))
        db.close()
    def test_reject_unsafe_overwrite_without_damaging_existing(self):
        build_index(self.source,"south_west",self.out,self.today)
        size=self.out.stat().st_size
        with self.assertRaises(FeedRejected):
            build_index(self.source,"south_west",self.out,self.today)
        self.assertEqual(self.out.stat().st_size,size)
    def test_support_gtfs_after_midnight(self):
        self.assertEqual(duration_seconds("26:15:30"),94530)
        self.assertIsNone(duration_seconds("99:99:99"))
    def test_reject_wrong_region_without_publishing_file(self):
        with self.assertRaises(FeedRejected):
            build_index(self.source,"west_midlands",self.out,self.today)
        self.assertFalse(self.out.exists())
