"""Independent stop-side release gate: fail closed on missing real-world proof."""
import unittest
from datetime import date, timedelta
from dataclasses import replace

from pilot.gtfs_engine import load_region
from pilot.test_gtfs_engine import make_feed
from pilot.journey_options import journey_options
from pilot.pedestrian_graph import PedestrianGraph
from pilot.transfer_connector_gate import (
    StopSideReview, independently_reviewed_links,
)

TODAY = date(2026, 10, 28)


class StopSideGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=load_region(make_feed(),"Coventry","fixture",
                                 date(2026,10,26),sha256="fixture")

    def graph(self, centreline=False, disconnected=False):
        g=PedestrianGraph("field-reviewed-osm")
        path=["B","C"] if not disconnected else ["B"]
        stops=self.snapshot.stops
        if not disconnected:
            g.add_way("way",[(s,stops[s].lat,stops[s].lon) for s in path],
                      {"highway":"residential","sidewalk":"both"}
                      if centreline else {"highway":"footway"})
        else:
            for key in ("B","C"):
                s=stops[key]
                g.add_way("alone-"+key,[
                    (key,s.lat,s.lon),
                    ("spur-"+key,s.lat+0.000001,s.lon)],
                    {"highway":"footway"})
        return g

    def review(self,key,graph):
        s=self.snapshot.stops[key]
        point=(s.lat,s.lon)
        return StopSideReview(
            stop_id=key,osm_node_id=key,atco_code=key,
            reviewer="independent field observer",
            reviewed_on=TODAY,method="ON_SITE_FIELD_CHECK",
            evidence_ref="fixture-review-"+key,
            graph_sha256=graph.source_sha256,
            gtfs_sha256=self.snapshot.source_sha256,
            stop_side="PAVEMENT_BY_STOP",
            crossing_checked=True,pavement_access_checked=True,
            to_graph=True,from_graph=True,
            geometry=(point,point),metres=0,seconds=0)

    def links(self,graph,updates=None):
        a=self.review("B",graph);b=self.review("C",graph)
        if updates:
            for target,changes in updates:
                if target=="B":a=replace(a,**changes)
                else:b=replace(b,**changes)
        return independently_reviewed_links(graph,self.snapshot,[a,b],TODAY)

    def test_reviewed_stop_sides_and_shared_footway_create_transfer(self):
        g=self.graph()
        x=self.links(g)
        self.assertEqual(x["outcome"],"OK")
        self.assertTrue(x["links"])
        self.assertTrue(all(w.verified for w in x["links"]))
        self.assertFalse(x["selectable"])

    def test_interchange_edges_propagate_to_real_journey_research(self):
        g=self.graph()
        x=self.links(g)
        result=journey_options(self.snapshot,"B","D",8*3600+10*60,
                               footpaths=x["links"])
        self.assertEqual(result["outcome"],"OK")
        self.assertIn("NO_ACCESSIBILITY_PROOF",result["results"][0]["warnings"])

    def test_stop_code_match_alone_does_not_authorize(self):
        g=self.graph()
        x=self.links(g,[("B",{"pavement_access_checked":False})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_unreviewed_crossing_is_not_assumed_safe(self):
        g=self.graph()
        x=self.links(g,[("B",{"crossing_checked":False})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_stale_review_is_rejected(self):
        g=self.graph()
        x=self.links(g,[("C",{"reviewed_on":TODAY-timedelta(days=181)})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_wrong_osm_snapshot_is_rejected(self):
        g=self.graph()
        x=self.links(g,[("C",{"graph_sha256":"unrelated-osm"})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_wrong_gtfs_snapshot_is_rejected(self):
        g=self.graph()
        x=self.links(g,[("C",{"gtfs_sha256":"unrelated-bus-feed"})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_wrong_side_and_stop_code_rejected(self):
        g=self.graph()
        x=self.links(g,[("B",{"atco_code":"opposite-side"})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")
        y=self.links(g,[("B",{"stop_side":"ROAD_CENTRELINE"})])
        self.assertEqual(y["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_unapproved_auto_proximity_is_rejected(self):
        g=self.graph()
        x=self.links(g,[("B",{"method":"NEAREST_OSM_NODE"})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_wrong_geometry_endpoint_is_rejected(self):
        g=self.graph()
        x=self.links(g,[("C",{"geometry":((52.0,-1.6),(52.0,-1.6))})])
        self.assertEqual(x["outcome"],"ACCESS_EVIDENCE_MISSING")

    def test_road_centreline_not_promoted_to_verified_footway(self):
        g=self.graph(centreline=True)
        x=self.links(g)
        self.assertEqual(x["outcome"],"WALK_TOPOLOGY_MISSING")
        self.assertFalse(x["links"])

    def test_nearby_unconnected_walk_is_not_invented(self):
        g=self.graph(disconnected=True)
        x=self.links(g)
        self.assertEqual(x["outcome"],"WALK_TOPOLOGY_MISSING")

    def test_one_way_stop_side_transfer(self):
        g=self.graph()
        x=self.links(g,[("B",{"to_graph":False})])
        self.assertTrue(all(w.a!="B" for w in x["links"]))

    def test_duplicate_review_fails_entire_batch(self):
        g=self.graph()
        a=self.review("B",g)
        result=independently_reviewed_links(
            g,self.snapshot,[a,a,self.review("C",g)],TODAY)
        self.assertEqual(result["outcome"],"EVIDENCE_CONFLICT")

    def test_nearby_real_crosswalk_data_still_zero_release_anchors(self):
        # Existing 27 Oct crosswalk audit proved identifier coincidence
        # only, NOT the independently observed boarding kerb or crossing.
        from pathlib import Path
        import json
        evidence=json.loads((Path(__file__).parent/
                        "real-stop-crosswalk-evidence-2026-10-27.json").read_text())
        for city in evidence["cities"]:
            self.assertEqual(city["autoVerifiedStopAnchors"],0)
            self.assertFalse(city["usableInRouting"])


if __name__ == "__main__":
    unittest.main()
