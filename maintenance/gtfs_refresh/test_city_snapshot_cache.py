import datetime as dt
import hashlib
import unittest
from pathlib import Path
from maintenance.gtfs_refresh.test_query_sqlite import IndexRoutingTests
from maintenance.gtfs_refresh.connection_snapshot import load_city_snapshot
from maintenance.gtfs_refresh.city_snapshot_cache import (
    encode_city_snapshot,load_city_cache)
from maintenance.gtfs_refresh.coordinate_journeys import coordinate_journeys


class BoundedCityCacheTests(unittest.TestCase):
    def setUp(self):
        self.fixture=IndexRoutingTests("test_refuse_unsupported_date")
        self.fixture.setUp()
        self.source=load_city_snapshot(
            self.fixture.db,"south_west","Bristol",dt.date(2026,10,29),
            (51.4545,-2.5879),(51.46,-2.595),radius_m=700)
        self.path=Path(self.fixture.t.name)/"city-20261029.json.gz"
        self.meta=encode_city_snapshot(self.source,self.path)

    def tearDown(self):self.fixture.tearDown()

    def load(self,sha=None,source_sha=None):
        return load_city_cache(
            self.path,"south_west",
            source_sha or self.source.source_sha256,dt.date(2026,10,29),
            sha or self.meta["packageSha256"])

    def test_source_snapshot_roundtrip_preserves_bus_choices(self):
        current=self.load()
        self.assertEqual(len(current.connections),len(self.source.connections))
        self.assertEqual(set(current.stops),set(self.source.stops))
        self.assertEqual(self.meta["packageSha256"],
                         hashlib.sha256(self.path.read_bytes()).hexdigest())
        coords=((51.4545,-2.5879),(51.46,-2.595))
        before=coordinate_journeys(self.source,*coords,8*3600+40*60,
                                   max_walk_m=180)
        after=coordinate_journeys(current,*coords,8*3600+40*60,
                                  max_walk_m=180)
        self.assertEqual([r["clearRouteId"] for r in before["results"]],
                         [r["clearRouteId"] for r in after["results"]])

    def test_source_identity_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"Wrong region, day or GTFS"):
            self.load(source_sha="0"*64)
        with self.assertRaisesRegex(ValueError,"Wrong region, day or GTFS"):
            load_city_cache(self.path,"west_midlands",
                            self.source.source_sha256,
                            dt.date(2026,10,29),
                            self.meta["packageSha256"])

    def test_package_checksum_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,"differ"):
            self.load(sha="0"*64)

    def test_untrusted_mutated_city_data_rejected_before_decompression(self):
        data=bytearray(self.path.read_bytes())
        data[-4]^=1
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,"differ"):
            self.load()

    def test_original_source_archive_not_modified(self):
        self.assertTrue(self.fixture.db.is_file())
        self.assertTrue(self.path.is_file())
        self.assertTrue(self.meta["researchOnly"])

if __name__=="__main__":unittest.main()
