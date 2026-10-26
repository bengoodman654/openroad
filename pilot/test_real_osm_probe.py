"""Deterministic contract checks for the real-data reconnaissance wrapper."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pilot.pedestrian_graph import PedestrianGraph
from pilot.real_osm_probe import audit_city


class RealOSMProbeTests(unittest.TestCase):
    def test_unverified_osm_stop_candidates_not_sold_as_walkable_gtfs(self):
        graph=PedestrianGraph("sample-osm")
        a=(52.4081,-1.5106)
        b=(52.4090,-1.5106)
        for i in range(11):
            graph.add_way(f"W{i}",[("N1",*a),("N2",*b)],
                          {"highway":"footway"})
        graph.transit_stops={
            "BS1":{"osmNode":"BS1","atcoCode":"43000001",
                   "name":"Bus 1","lat":a[0],"lon":a[1]},
            "BS2":{"osmNode":"BS2","atcoCode":"43000002",
                   "name":"Bus 2","lat":b[0],"lon":b[1]},
        }
        with patch("pilot.real_osm_probe.load_osm_pbf_offhost",
                   return_value=graph), patch(
                       "pilot.real_osm_probe.Path.stat",
                       return_value=SimpleNamespace(st_size=1234)):
            result=audit_city("Coventry","unused.osm.pbf")
        self.assertEqual(result["mappedOSMBusStopNodes"],2)
        self.assertEqual(result["osmStopsWithAtcoTags"],2)
        self.assertEqual(result["osmStopsWithNearbyWalkNode"],2)
        self.assertEqual(result["diagnosticStopPairs"],2)
        self.assertTrue(result["topologicallyConnectedPairs"]>=1)
        self.assertFalse(result["gtfsCrosswalkVerified"])
        self.assertFalse(result["streetAccessFieldVerified"])
        self.assertFalse(result["productionReleaseReady"])


if __name__=="__main__":
    unittest.main()
