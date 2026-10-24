"""Deterministic offline checks. Published route metadata is real; GTFS trip times below are synthetic."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date
from zipfile import ZipFile
from gtfs_fixture_adapter import GTFSFixture, GTFSFixtureError, seconds
from reference import location, identity

REFERENCE=Path(__file__).resolve().parents[2]/"docs/public-transport-v2/fixtures/bristol_coventry_reference.json"

def csv_bytes(columns,rows):
    buff=io.StringIO(newline="")
    writer=csv.DictWriter(buff,fieldnames=columns,lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buff.getvalue().encode("utf-8")

def archive(path,change=None):
    """Synthetic, tiny GTFS demonstrating real-published service numbers, NOT real departure times."""
    tables={
      "routes.txt":csv_bytes(["route_id","agency_id","route_short_name","route_long_name"],[
        dict(route_id="first:75",agency_id="first",route_short_name="75",route_long_name="Cribbs Causeway to Hengrove"),
        dict(route_id="nxc:11",agency_id="nxc",route_short_name="11",route_long_name="Coventry to Leamington Spa"),
        dict(route_id="nxc:12X",agency_id="nxc",route_short_name="12X",route_long_name="Coventry to Warwick University"),
        dict(route_id="other:11",agency_id="other",route_short_name="11",route_long_name="Other operator's 11")]),
      "stops.txt":csv_bytes(["stop_id","stop_name"],[
        dict(stop_id="BRI_A",stop_name="Cribbs Causeway Bus Station"),
        dict(stop_id="BRI_B",stop_name="Hengrove Bus Depot"),
        dict(stop_id="COV_A",stop_name="Coventry Pool Meadow"),
        dict(stop_id="COV_B",stop_name="University of Warwick"),
        dict(stop_id="COV_C",stop_name="Leamington Spa"),
        dict(stop_id="OTHER",stop_name="Unrelated stop")]),
      "trips.txt":csv_bytes(["route_id","service_id","trip_id"],[
        dict(route_id="first:75",service_id="MON",trip_id="first75"),
        dict(route_id="nxc:11",service_id="MON",trip_id="nxc11"),
        dict(route_id="nxc:12X",service_id="MON",trip_id="nxc12x"),
        dict(route_id="other:11",service_id="MON",trip_id="other11")]),
      "stop_times.txt":csv_bytes(["trip_id","stop_id","stop_sequence","arrival_time","departure_time"],[
        dict(trip_id="first75",stop_id="BRI_A",stop_sequence=1,arrival_time="23:58:00",departure_time="23:58:00"),
        dict(trip_id="first75",stop_id="BRI_B",stop_sequence=2,arrival_time="25:01:00",departure_time="25:01:00"),
        dict(trip_id="nxc11",stop_id="COV_A",stop_sequence=1,arrival_time="08:00:00",departure_time="08:00:00"),
        dict(trip_id="nxc11",stop_id="COV_B",stop_sequence=2,arrival_time="08:30:00",departure_time="08:30:00"),
        dict(trip_id="nxc11",stop_id="COV_C",stop_sequence=3,arrival_time="09:00:00",departure_time="09:00:00"),
        dict(trip_id="nxc12x",stop_id="COV_A",stop_sequence=1,arrival_time="09:00:00",departure_time="09:00:00"),
        dict(trip_id="nxc12x",stop_id="COV_B",stop_sequence=2,arrival_time="09:30:00",departure_time="09:30:00"),
        dict(trip_id="other11",stop_id="OTHER",stop_sequence=1,arrival_time="08:00:00",departure_time="08:00:00")]),
      "calendar.txt":csv_bytes(["service_id","start_date","end_date","monday","tuesday","wednesday","thursday","friday","saturday","sunday"],[
        dict(service_id="MON",start_date="20261001",end_date="20261130",monday="1",tuesday="1",wednesday="1",thursday="1",friday="1",saturday="0",sunday="0")]),
      "calendar_dates.txt":csv_bytes(["service_id","date","exception_type"],[
        dict(service_id="MON",date="20261024",exception_type="1"),
        dict(service_id="MON",date="20261026",exception_type="2")]),
    }
    if change:change(tables)
    with ZipFile(path,"w") as dest:
        for name,data in tables.items():
            dest.writestr(name,data)

class BristolCoventryReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref=json.loads(REFERENCE.read_text(encoding="utf-8"))
        cls.cases={c["id"]:c for c in cls.ref["cases"]}

    def test_published_reference_scope_is_honest(self):
        self.assertEqual(len(self.cases),4)
        self.assertIn("Not raw GTFS",self.ref["source_notice"])
        for case in self.cases.values():
            self.assertEqual(case["validation"],"public-route-metadata-only")
            self.assertTrue(case["evidence"])
            self.assertTrue(all(e["url"].startswith("https://") for e in case["evidence"]))
            self.assertTrue(all(e["assertions"] for e in case["evidence"]))
            self.assertIn(case["mode"],["bus"])

    def test_real_published_bristol_75(self):
        x=self.cases["BRI-75"]
        self.assertEqual((x["area"],x["line"],x["provider"]),("Bristol","75","First Bus"))
        self.assertEqual(x["endpoints"],["Cribbs Causeway","Hengrove"])

    def test_real_published_coventry_11_12x_and_9(self):
        a,b,c=(self.cases[i] for i in ("COV-11","COV-12X","COV-9"))
        self.assertEqual((a["line"],a["endpoints"]),("11",["Coventry","Leamington Spa"]))
        self.assertIn("Kenilworth",a["via"])
        self.assertEqual((b["line"],c["line"]),("12X","9"))

    def test_distant_coventry_selection_overrides_bristol_gps(self):
        self.assertEqual(location(explicit="Coventry",gps="Bristol",opt_in=True),("explicit","Coventry"))

    def test_provider_namespacing_prevents_11_collision(self):
        self.assertNotEqual(identity("nxc","line","11"),identity("other","line","11"))

class GTFSOfflineAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"synthetic.zip"
        archive(self.path)
        self.gtfs=GTFSFixture.open(self.path)
    def tearDown(self):
        self.tmp.cleanup()

    def test_can_index_two_real_world_named_areas_from_synthetic_gtfs(self):
        self.assertEqual(self.gtfs.services("75",date(2026,10,23))[0]["route_id"],"first:75")
        self.assertEqual(len(self.gtfs.services("11",date(2026,10,23))),2)
        self.assertEqual(self.gtfs.services("12X",date(2026,10,23))[0]["route_id"],"nxc:12X")

    def test_synthetic_stop_sequence_order(self):
        self.assertEqual(self.gtfs.trip_stop_names("nxc11"),["Coventry Pool Meadow","University of Warwick","Leamington Spa"])

    def test_exception_adds_saturday_and_removes_monday(self):
        self.assertTrue(self.gtfs.active("MON",date(2026,10,24)))
        self.assertFalse(self.gtfs.active("MON",date(2026,10,26)))
        self.assertFalse(self.gtfs.services("75",date(2026,10,26)))

    def test_gtfs_25_hour_time_is_next_service_day(self):
        self.assertEqual(seconds("25:01:00"),25*3600+60)
        self.assertEqual(self.gtfs.stop_times["first75"][1]["arrival_time"],"25:01:00")

    def test_unknown_line_no_match_not_coverage_failure(self):
        self.assertEqual(self.gtfs.services("9999",date(2026,10,23)),[])

    def test_invalid_timetable_sequence_is_rejected(self):
        def corrupt(tables):
            tables["stop_times.txt"]=tables["stop_times.txt"].replace(b"09:00:00,09:00:00",b"06:00:00,06:00:00")
        archive(self.path,corrupt)
        with self.assertRaises(GTFSFixtureError):
            GTFSFixture.open(self.path)

    def test_unresolved_stop_ref_is_rejected(self):
        def corrupt(tables):tables["stop_times.txt"]=tables["stop_times.txt"].replace(b"COV_B",b"FAKE_STOP")
        archive(self.path,corrupt)
        with self.assertRaises(GTFSFixtureError):
            GTFSFixture.open(self.path)

    def test_required_file_missing_is_rejected(self):
        def corrupt(tables):tables.pop("trips.txt")
        archive(self.path,corrupt)
        with self.assertRaises(GTFSFixtureError):
            GTFSFixture.open(self.path)

    def test_duplicate_member_is_rejected(self):
        with ZipFile(self.path,"a") as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                z.writestr("routes.txt",b"route_id,route_short_name\n")
        with self.assertRaises(GTFSFixtureError):
            GTFSFixture.open(self.path)

    def test_archive_size_cap(self):
        with self.assertRaises(GTFSFixtureError):
            GTFSFixture.open(self.path,max_bytes=40)

    def test_no_network_or_hostside_import_is_needed(self):
        self.assertEqual(self.gtfs.routes["first:75"]["agency_id"],"first")
        self.assertIn("nxc11",self.gtfs.stop_times)

if __name__=="__main__":unittest.main()
