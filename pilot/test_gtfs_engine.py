"""Deterministic synthetic tests for the isolated OpenRoad pilot engine."""
import unittest
from pilot.gtfs_engine import *
import csv
import io
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import date, timezone


def gtfs_csv(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


def make_feed(exceptions=None, extra_trip=False):
    tables = {
        "agency.txt": gtfs_csv(
            ["agency_id","agency_name","agency_url","agency_timezone"],
            [["OP_A","Example A","https://example.invalid","Europe/London"],
             ["OP_B","Example B","https://example.invalid","Europe/London"]]),
        "stops.txt": gtfs_csv(
            ["stop_id","stop_name","stop_lat","stop_lon"],
            [["A","Start",52.4081,-1.5106],["B","Middle",52.4090,-1.5106],
             ["C","Transfer",52.4100,-1.5106],["D","Finish",52.4110,-1.5106],
             ["O","Outside",53.1000,-2.4000]]),
        "routes.txt": gtfs_csv(
            ["route_id","agency_id","route_short_name","route_type"],
            [["RA","OP_A","75","3"],["RB","OP_B","75","3"],["RC","OP_A","90","3"],["RT","OP_A","T","0"]]),
        "calendar.txt": gtfs_csv(
            ["service_id","monday","tuesday","wednesday","thursday","friday","saturday","sunday","start_date","end_date"],
            [["WEEK","1","1","1","1","1","0","0","20261001","20261130"],
             ["HOL","0","0","0","0","0","0","0","20261001","20261130"]]),
        "calendar_dates.txt": gtfs_csv(
            ["service_id","date","exception_type"], exceptions or []),
        "trips.txt": gtfs_csv(
            ["trip_id","route_id","service_id"],
            [["T1","RA","WEEK"],["T2","RB","WEEK"],["T3","RC","WEEK"],
             ["T4","RC","WEEK"],["T5","RC","HOL"],["T6","RA","WEEK"],["TRAM","RT","WEEK"]] +
            ([["T7","RA","WEEK"]] if extra_trip else [])),
        "feed_info.txt": gtfs_csv(
            ["feed_publisher_name","feed_publisher_url","feed_lang","feed_start_date","feed_end_date","feed_version"],
            [["Synthetic Research Fixture","https://example.invalid","en","20261001","20261130","synthetic_01"]]),
    }
    st = [
        ["T1","08:00:00","08:00:00","A",1,0,0],
        ["T1","08:10:00","08:10:00","B",2,1,0],
        ["T1","08:20:00","08:20:00","C",3,0,0],
        ["T2","08:03:00","08:03:00","A",1,0,0],
        ["T2","08:12:00","08:12:00","B",2,0,0],
        ["T2","08:25:00","08:25:00","C",3,0,0],
        ["T3","08:23:00","08:23:00","C",1,0,0],
        ["T3","08:33:00","08:33:00","D",2,0,0],
        ["T4","08:21:00","08:21:00","C",1,0,0],
        ["T4","08:32:00","08:32:00","D",2,0,0],
        ["T5","09:00:00","09:00:00","A",1,0,0],
        ["T5","09:20:00","09:20:00","D",2,0,0],
        ["T6","25:00:00","25:00:00","A",1,0,0],
        ["T6","25:10:00","25:10:00","B",2,0,0],
        ["TRAM","07:50:00","07:50:00","A",1,0,0],
        ["TRAM","08:05:00","08:05:00","D",2,0,0],
    ]
    if extra_trip:
        st += [
            ["T7","10:00:00","10:00:00","A",1,0,0],
            ["T7","10:15:00","10:15:00","O",2,0,0],
            ["T7","10:30:00","10:30:00","C",3,0,0],
        ]
    tables["stop_times.txt"] = gtfs_csv(
        ["trip_id","arrival_time","departure_time","stop_id","stop_sequence","pickup_type","drop_off_type"], st)
    buf = io.BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED) as z:
        for name,contents in tables.items():
            z.writestr(name,contents)
    buf.seek(0)
    return buf


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.buf=make_feed()
        cls.snapshot=load_region(cls.buf,"Coventry","fixture",date(2026,10,26),sha256="synthetic")

    def test_01_gtfs_over_24_hours(self):
        self.assertEqual(gtfs_seconds("25:10:00"),90600)

    def test_02_gtfs_invalid_time(self):
        with self.assertRaises(ValueError):gtfs_seconds("24:75:00")

    def test_03_gtfs_dst_fall_is_elapsed(self):
        instant=gtfs_utc(date(2026,10,25),2*3600)
        self.assertEqual(instant.isoformat(),"2026-10-25T02:00:00+00:00")

    def test_04_gtfs_dst_spring_is_elapsed(self):
        instant=gtfs_utc(date(2026,3,29),2*3600)
        self.assertEqual(instant.isoformat(),"2026-03-29T01:00:00+00:00")

    def test_05_calendar_exception_remove_add(self):
        with ZipFile(make_feed(exceptions=[["WEEK","20261026","2"],["HOL","20261026","1"]])) as z:
            self.assertEqual(active_services(z,date(2026,10,26)),{"HOL"})

    def test_06_same_line_different_operators(self):
        s=self.snapshot
        self.assertNotEqual(s.trips["T1"][0],s.trips["T2"][0])
        self.assertEqual(s.routes[s.trips["T1"][0]][0],"75")
        self.assertEqual(s.routes[s.trips["T2"][0]][0],"75")

    def test_07_real_sequence_direct(self):
        r=plan_stops(self.snapshot,"A","C",gtfs_seconds("07:55:00"))
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["arrival"],gtfs_seconds("08:20:00"))
        self.assertEqual(r["legs"][0]["publicLine"],"75")
        self.assertIn("T1",r["legs"][0]["tripOccurrence"])

    def test_08_transfer_buffer_excludes_one_minute(self):
        r=plan_stops(self.snapshot,"A","D",gtfs_seconds("07:55:00"),transfer_seconds=120)
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["arrival"],gtfs_seconds("08:33:00"))
        self.assertNotIn("T4",repr(r["legs"]))

    def test_09_stricter_transfer_rejects_path(self):
        r=plan_stops(self.snapshot,"A","D",gtfs_seconds("07:55:00"),transfer_seconds=300)
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_10_transfer_limit(self):
        r=plan_stops(self.snapshot,"A","D",gtfs_seconds("07:55:00"),max_transfers=0)
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_11_pickup_restriction(self):
        r=plan_stops(self.snapshot,"B","C",gtfs_seconds("08:08:00"),transfer_seconds=0)
        self.assertEqual(r["outcome"],"OK")
        self.assertIn("T2",r["legs"][0]["tripOccurrence"])

    def test_12_known_graph_no_reverse(self):
        r=plan_stops(self.snapshot,"D","A",gtfs_seconds("07:55:00"))
        self.assertEqual(r["outcome"],"NO_JOURNEY")

    def test_13_unknown_stop_means_coverage(self):
        r=plan_stops(self.snapshot,"UNKNOWN","A",gtfs_seconds("07:55:00"))
        self.assertEqual(r["outcome"],"COVERAGE_MISSING")

    def test_14_clipped_trip_not_invented(self):
        s=load_region(make_feed(extra_trip=True),"Coventry","fixture",date(2026,10,26),sha256="synthetic")
        self.assertTrue(all(c.trip!="T7" for c in s.connections))

    def test_15_service_date_outside_feed(self):
        with self.assertRaisesRegex(ValueError,"COVERAGE_MISSING"):
            load_region(make_feed(),"Coventry","fixture",date(2027,1,1),sha256="synthetic")

    def test_16_calendar_holiday_trip_excluded(self):
        self.assertNotIn("T5",self.snapshot.trips)

    def test_17_service_overnight_trip(self):
        r=plan_stops(self.snapshot,"A","B",gtfs_seconds("24:55:00"))
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["arrival"],gtfs_seconds("25:10:00"))

    def test_19_first_last_mile_estimates_are_labelled(self):
        s=self.snapshot
        origin=(52.4076,-1.5106)
        destination=(52.4105,-1.5106)
        r=plan_coordinates(s,origin,destination,gtfs_seconds("07:54:00"),max_total_walk_m=250)
        self.assertEqual(r["outcome"],"OK")
        self.assertTrue(any(x["mode"]=="WALK_ESTIMATE" for x in r["legs"]))
        self.assertIn("NO_ACCESSIBILITY_PROOF",r["warnings"])

    def test_20_walking_hard_cap_rejected(self):
        s=self.snapshot
        origin=(52.4500,-1.5106)
        destination=(52.4105,-1.5106)
        r=plan_coordinates(s,origin,destination,gtfs_seconds("07:54:00"),max_total_walk_m=250)
        self.assertEqual(r["outcome"],"NO_JOURNEY")
        self.assertEqual(r["reasonCode"],"WALKING_LIMIT")

    def test_21_non_bus_mode_is_excluded(self):
        self.assertNotIn("TRAM",self.snapshot.trips)

    def test_22_snapshot_sqlite_index_is_consistent(self):
        import sqlite3
        s=self.snapshot
        db=sqlite3.connect(":memory:")
        populate_sqlite(s,db)
        sid=db.execute("SELECT snapshot_key FROM snapshots WHERE city=?",(s.city,)).fetchone()[0]
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM connections WHERE snapshot_key=?",
            (sid,)).fetchone()[0],len(s.connections))
        with self.assertRaisesRegex(ValueError,"Duplicate immutable"):
            populate_sqlite(s,db)
        db.close()

    def test_23_serving_epochs_include_service_date(self):
        import sqlite3
        db=sqlite3.connect(":memory:")
        a=self.snapshot
        b=load_region(make_feed(),"Coventry","fixture",date(2026,10,27),sha256="synthetic")
        populate_sqlite(a,db)
        populate_sqlite(b,db)
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM snapshots").fetchone()[0],2)
        db.close()

    def test_18_origin_equals_destination(self):
        r=plan_stops(self.snapshot,"A","A",gtfs_seconds("12:00:00"))
        self.assertEqual(r["outcome"],"OK")
        self.assertEqual(r["legs"],[])


if __name__ == "__main__":
    unittest.main(verbosity=2)
