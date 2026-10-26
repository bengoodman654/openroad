"""Off-host Osmium parser smoke test using a tiny reference-complete OSM XML.

The Python import is optional for the core pilot; GitHub's full-suite job
installs pyosmium and runs this against a real parser, not mocked objects.
"""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

from pilot.pedestrian_graph import load_osm_pbf_offhost

OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="OpenRoad synthetic test">
  <node id="1" lat="52.4081" lon="-1.5106" />
  <node id="2" lat="52.4090" lon="-1.5106">
    <tag k="highway" v="bus_stop"/>
    <tag k="naptan:AtcoCode" v="43000001234"/>
    <tag k="name" v="Synthetic High Street"/>
  </node>
  <node id="3" lat="52.4100" lon="-1.5106">
    <tag k="barrier" v="gate"/>
    <tag k="access" v="private"/>
  </node>
  <node id="4" lat="52.4110" lon="-1.5106" />
  <node id="5" lat="52.4120" lon="-1.5106" />
  <way id="100">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="footway"/>
  </way>
  <way id="101">
    <nd ref="4"/><nd ref="5"/>
    <tag k="highway" v="path"/>
    <tag k="foot" v="no"/>
  </way>
</osm>"""


@unittest.skipUnless(importlib.util.find_spec("osmium"),
                     "Optional pyosmium not installed in this runtime")
class OSMAdapterTests(unittest.TestCase):
    def test_parser_coordinates_access_barrier_and_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "small-complete.osm"
            data = OSM_XML.encode("utf-8")
            path.write_bytes(data)
            graph = load_osm_pbf_offhost(str(path),
                                          centre=(52.4090,-1.5106),
                                          radius_m=250)
            self.assertEqual(graph.source_sha256,
                             hashlib.sha256(data).hexdigest())
            self.assertIn("2",graph.nodes)
            self.assertEqual(graph.transit_stops["2"]["atcoCode"],
                             "43000001234")
            self.assertEqual(graph.transit_stops["2"]["crosswalk"],
                             "UNVERIFIED_OSM_TAG")
            self.assertEqual(graph.accepted_ways,1)
            self.assertIsNotNone(graph.route("1","2",250))
            self.assertIsNone(graph.route("1","3",300))
            self.assertNotIn("4",graph.nodes)
            self.assertNotIn("5",graph.nodes)


if __name__ == "__main__":
    unittest.main()
