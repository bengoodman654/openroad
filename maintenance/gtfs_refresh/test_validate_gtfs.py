import csv
import datetime as dt
import io
import pathlib
import tempfile
import unittest
import zipfile
from maintenance.gtfs_refresh.validate_gtfs import validate_archive, FeedRejected

class FreshFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/"feed.zip"
        self.today=dt.date(2026,10,29)

    def tearDown(self):
        self.tmp.cleanup()

    def feed(self,city="bristol",future=True,missing=None,duplicate=False):
        lat,lon=(51.4545,-2.5879) if city=="bristol" else (52.4068,-1.5197)
        content={
            "agency.txt":"agency_id,agency_name,agency_url,agency_timezone\nA,Test,https://example.org,Europe/London\n",
            "routes.txt":"route_id,route_short_name\n"+ "".join(f"R{i},B{i}\n" for i in range(15)),
            "trips.txt":"route_id,service_id,trip_id\n"+ "".join(f"R{i%15},S,T{i}\n" for i in range(80)),
            "stops.txt":"stop_id,stop_name,stop_lat,stop_lon\n"+
                 "".join(f"{i},Stop {i},{lat+i*0.00001},{lon}\n" for i in range(120)),
            "stop_times.txt":"trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"+
                 "".join(f"T{i},09:00:00,09:00:00,0,1\n" for i in range(80)),
            "calendar.txt":"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"+
                 "S,1,1,1,1,1,1,1,20261001,"+("20270201" if future else "20261029")+"\n",
            "calendar_dates.txt":"service_id,date,exception_type\nS,20261101,1\n",
        }
        if missing:content.pop(missing,None)
        with zipfile.ZipFile(self.path,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for name,data in content.items():z.writestr(name,data)
            if duplicate:z.writestr("nested/stops.txt",content["stops.txt"])
        # Unit fixture small: production minimum size is patched only for
        # this fixture by adding a bounded harmless member.
        with zipfile.ZipFile(self.path,"a") as z:z.writestr("notes.txt","x"*11000)
        return self.path

    def test_valid_bristol_and_coventry_sources(self):
        from unittest.mock import patch
        with patch("maintenance.gtfs_refresh.validate_gtfs.MINIMUM_DUMMY",True,create=True):
            a=validate_archive(self.feed("bristol"),"south_west",self.today)
            self.assertEqual(a["result"],"VALIDATED_SOURCE_ONLY")
            self.assertFalse(a["productionDeploymentApproved"])
            b=validate_archive(self.feed("coventry"),"west_midlands",self.today)
            self.assertGreaterEqual(b["stopsNearReferenceCity"],10)

    def test_rejects_wrong_region(self):
        with self.assertRaisesRegex(FeedRejected,"regional bus coverage"):
            validate_archive(self.feed("coventry"),"south_west",self.today)

    def test_rejects_expired_feed(self):
        with self.assertRaisesRegex(FeedRejected,"Future timetable"):
            validate_archive(self.feed(future=False),"south_west",self.today)

    def test_rejects_missing_table(self):
        with self.assertRaisesRegex(FeedRejected,"Missing required"):
            validate_archive(self.feed(missing="trips.txt"),"south_west",self.today)

    def test_rejects_ambiguous_duplicate_filename(self):
        with self.assertRaisesRegex(FeedRejected,"Ambiguous duplicate"):
            validate_archive(self.feed(duplicate=True),"south_west",self.today)

    def test_rejects_invalid_zip(self):
        self.path.write_text("not an archive")
        with self.assertRaises(FeedRejected):
            validate_archive(self.path,"south_west",self.today)
