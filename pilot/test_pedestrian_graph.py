"""Synthetic graph regressions: real topology, explicit stop connectors and flags."""
import unittest
from datetime import date

from pilot.gtfs_engine import load_region
from pilot.test_gtfs_engine import make_feed
from pilot.journey_options import Footpath, journey_options
from pilot.pedestrian_graph import (
    PedestrianGraph, StopAnchor, allows_pedestrians, foot_direction,
    link_stops, connected_stop_links, propose_stop_anchors,
)


class PedestrianGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_region(
            make_feed(), "Coventry", "fixture", date(2026,10,26),
            sha256="fixture")

    def place(self, name):
        s=self.snapshot.stops[name]
        return (s.lat,s.lon)

    def graph(self):
        g=PedestrianGraph("synthetic-osm")
        g.add_way("mapped-sidewalk",[
            (key,*self.place(key)) for key in ("A","B","C","D")],
            {"highway":"footway"})
        return g

    def anchor(self, key, verified=True, to_graph=True, from_graph=True):
        point=self.place(key)
        return StopAnchor(key,key,0,0,(point,point),verified,
                          "independent-fixture-check",
                          to_graph=to_graph,from_graph=from_graph)

    def test_01_connected_dedicated_path_has_real_geometry(self):
        g=self.graph()
        p=g.route("A","D",400)
        self.assertIsNotNone(p)
        self.assertEqual(p.node_ids,("A","B","C","D"))
        self.assertEqual(len(p.geometry),4)
        self.assertTrue(p.mapped_foot_geometry)

    def test_02_nearby_disconnected_islands_do_not_connect(self):
        g=PedestrianGraph("islands")
        for a,b in (("A","B"),("C","D")):
            g.add_way(a+b,[(x,*self.place(x)) for x in (a,b)],
                      {"highway":"footway"})
        self.assertIsNone(g.route("B","C",300))
        self.assertIsNone(link_stops(
            g,self.snapshot,self.anchor("B"),self.anchor("C"),300))

    def test_03_unverified_stop_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"independently verified"):
            link_stops(self.graph(),self.snapshot,
                       self.anchor("B",verified=False),self.anchor("C"),300)

    def test_04_wrong_side_snap_geometry_is_rejected(self):
        bad=StopAnchor("B","C",0,0,
                       (self.place("B"),self.place("B")),True,
                       "independent-fixture-check")
        with self.assertRaisesRegex(ValueError,"does not connect"):
            link_stops(self.graph(),self.snapshot,bad,self.anchor("C"),300)

    def test_05_foot_only_oneway_is_directional(self):
        g=PedestrianGraph("oneway")
        g.add_way("s",[(x,*self.place(x)) for x in ("B","C")],
                  {"highway":"footway","oneway:foot":"yes"})
        self.assertIsNotNone(g.route("B","C",300))
        self.assertIsNone(g.route("C","B",300))

    def test_06_car_oneway_does_not_limit_walking(self):
        g=PedestrianGraph("car-oneway")
        g.add_way("s",[(x,*self.place(x)) for x in ("B","C")],
                  {"highway":"footway","oneway":"yes"})
        self.assertIsNotNone(g.route("C","B",300))
        self.assertEqual(foot_direction({"oneway":"yes"}),0)

    def test_07_step_avoidance_is_not_accessibility_proof(self):
        g=PedestrianGraph("stairs")
        g.add_way("steps",[(x,*self.place(x)) for x in ("B","C")],
                  {"highway":"steps"})
        r=g.route("B","C",300)
        self.assertTrue(r.includes_steps)
        self.assertIsNone(g.route("B","C",300,avoid_steps=True))
        w=link_stops(g,self.snapshot,self.anchor("B"),self.anchor("C"),300)
        self.assertTrue(w.verified) # topology, NOT wheelchair access
        planned=journey_options(self.snapshot,"B","C",8*3600+10*60,
                                footpaths=[w])
        self.assertIn("NO_ACCESSIBILITY_PROOF",
                      planned["results"][0]["warnings"])
        self.assertIn("STEPS_PRESENT",
                      planned["results"][0]["warnings"])

    def test_08_private_and_foot_restricted_paths_excluded(self):
        self.assertFalse(allows_pedestrians(
            {"highway":"footway","foot":"private"}))
        self.assertFalse(allows_pedestrians(
            {"highway":"footway","access":"no"}))
        self.assertTrue(allows_pedestrians(
            {"highway":"footway","access":"no","foot":"yes"}))
        self.assertFalse(allows_pedestrians(
            {"highway":"footway","access:conditional":"no @ (Mo-Fr)"}))

    def test_09_unmapped_road_is_not_a_pedestrian_link(self):
        self.assertFalse(allows_pedestrians({"highway":"primary"}))
        self.assertFalse(allows_pedestrians(
            {"highway":"residential","sidewalk":"separate"}))
        self.assertTrue(allows_pedestrians(
            {"highway":"residential","sidewalk":"both"}))

    def test_10_barrier_node_blocks_transit_through_path(self):
        g=self.graph()
        g.block_node("C")
        self.assertIsNone(g.route("B","D",400))
        self.assertIsNone(g.route("A","C",400))

    def test_11_long_detour_exceeds_walk_cap(self):
        g=PedestrianGraph("detour")
        a=self.place("A");c=self.place("C")
        x=(a[0],a[1]+0.012)
        g.add_way("u",[("A",*a),("X",*x),("C",*c)],
                  {"highway":"footway"})
        self.assertIsNone(g.route("A","C",300))
        self.assertIsNotNone(g.route("A","C",3000))

    def test_12_real_graph_footpath_propagates_to_journey_map(self):
        g=self.graph()
        w=link_stops(g,self.snapshot,self.anchor("B"),self.anchor("C"),300)
        self.assertEqual((w.a,w.b),("B","C"))
        self.assertTrue(w.verified)
        self.assertEqual(w.provider,"OpenStreetMap")
        self.assertEqual(w.source_sha256,"synthetic-osm")
        r=journey_options(self.snapshot,"B","C",8*3600+10*60,
                          footpaths=[w])
        self.assertEqual(r["outcome"],"OK")
        leg=r["results"][0]["legs"][0]
        self.assertEqual(leg["mode"],"WALK")
        self.assertTrue(leg["geometryValidated"])
        self.assertEqual(len(leg["geometry"]),2)
        self.assertEqual(leg["geometrySource"],"OpenStreetMap")
        self.assertIn("NO_ACCESSIBILITY_PROOF",r["results"][0]["warnings"])

    def test_13_road_centreline_geometry_not_marked_verified(self):
        g=PedestrianGraph("approximated-road")
        g.add_way("road",[(x,*self.place(x)) for x in ("B","C")],
                  {"highway":"residential","sidewalk":"both"})
        w=link_stops(g,self.snapshot,self.anchor("B"),self.anchor("C"),300)
        self.assertFalse(w.verified)
        r=journey_options(self.snapshot,"B","C",8*3600+10*60,
                          footpaths=[w])
        self.assertIn("UNVERIFIED_WALK_GEOMETRY",
                      r["results"][0]["warnings"])

    def test_14_stop_anchor_direction_must_allow_disembarking(self):
        g=self.graph()
        dest=self.anchor("C",from_graph=False)
        self.assertIsNone(link_stops(
            g,self.snapshot,self.anchor("B"),dest,300))

    def test_15_offhost_links_are_bounded_and_connected(self):
        g=self.graph()
        anchors=[self.anchor(x) for x in ("A","B","C","D")]
        out=connected_stop_links(g,self.snapshot,anchors,
                                  max_walk_m=300,max_per_stop=1)
        self.assertEqual(len(out),4)
        self.assertTrue(all(w.geometry and w.source_sha256 for w in out))
        self.assertTrue(all(w.metres<=300 for w in out))

    def test_16_claimed_verified_footpath_without_source_rejected(self):
        untrusted=Footpath("B","C",120,120,True)
        with self.assertRaisesRegex(ValueError,"lacks geometry provenance"):
            journey_options(self.snapshot,"B","C",8*3600,
                            footpaths=[untrusted])

    def test_17_unknown_and_duplicate_anchors_fail_closed(self):
        g=self.graph()
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            connected_stop_links(g,self.snapshot,
                                 [self.anchor("B"),self.anchor("B")])

    def test_18_nonmatching_osm_node_coordinate_rejected(self):
        g=self.graph()
        with self.assertRaisesRegex(ValueError,"Conflicting coordinates"):
            g.add_way("bad",[("B",53.0,-1.51),("C",*self.place("C"))],
                      {"highway":"footway"})


    def test_19_crossing_lines_without_shared_osm_node_do_not_join(self):
        g=PedestrianGraph("unshared-crossing")
        a=self.place("A")
        d=self.place("D")
        g.add_way("north-south",[("A",*a),("D",*d)],
                  {"highway":"footway"})
        g.add_way("east-west",[
            ("LEFT",52.4095,-1.5110),("RIGHT",52.4095,-1.5102)],
            {"highway":"footway"})
        self.assertIsNone(g.route("A","RIGHT",500))

    def test_20_verified_route_cannot_fake_distance(self):
        fake=Footpath("B","C",10,10,True,
                      (self.place("B"),self.place("C")),
                      "fixture","source-hash")
        with self.assertRaisesRegex(ValueError,"disagrees with distance"):
            journey_options(self.snapshot,"B","C",8*3600,
                            footpaths=[fake])

    def test_21_unknown_pedestrian_oneway_is_not_guessed(self):
        self.assertFalse(allows_pedestrians(
            {"highway":"footway","oneway:foot":"variable"}))


    def test_22_nearest_node_is_only_a_nonroutable_suggestion(self):
        g=self.graph()
        suggestions=propose_stop_anchors(g,self.snapshot,max_snap_m=10)
        match=[p for p in suggestions if p.stop_id=="B"]
        self.assertEqual(len(match),1)
        self.assertEqual(match[0].node_id,"B")
        self.assertEqual(match[0].status,"UNVERIFIED_NOT_ROUTABLE")
        self.assertFalse(hasattr(match[0],"verified"))

    def test_23_barrier_nodes_cannot_be_suggested_as_anchors(self):
        g=self.graph()
        g.block_node("B")
        suggestions=propose_stop_anchors(g,self.snapshot,max_snap_m=10)
        self.assertFalse(any(x.stop_id=="B" for x in suggestions))



    def test_24_graph_walk_can_be_cancelled_before_start(self):
        from pilot.request_lifecycle import SearchCancelled
        g = self.graph()
        with self.assertRaises(SearchCancelled):
            g.route("A", "D", 500, cancel_check=lambda: True)

    def test_25_graph_walk_cancelled_during_expansion_not_no_route(self):
        from pilot.request_lifecycle import SearchCancelled
        g = self.graph()
        calls = [0]

        def cancel():
            calls[0] += 1
            return calls[0] >= 2

        with self.assertRaises(SearchCancelled):
            g.route("A", "D", 500, cancel_check=cancel)
        self.assertGreaterEqual(calls[0], 2)

    def test_26_stop_link_propagates_cancellation(self):
        from pilot.request_lifecycle import SearchCancelled
        g = self.graph()
        with self.assertRaises(SearchCancelled):
            link_stops(g, self.snapshot, self.anchor("B"),
                       self.anchor("C"), 300, cancel_check=lambda: True)

    def test_27_batch_stop_links_interrupt_bounded_scan(self):
        from pilot.request_lifecycle import SearchCancelled
        g = self.graph()
        anchors = [self.anchor(x) for x in ("A", "B", "C", "D")]
        with self.assertRaises(SearchCancelled):
            connected_stop_links(g, self.snapshot, anchors,
                                 max_walk_m=300, cancel_check=lambda: True)

    def test_28_invalid_cancellation_check_rejected(self):
        g = self.graph()
        with self.assertRaises(ValueError):
            g.route("A", "D", 500, cancel_check="invalid")

if __name__ == "__main__":
    unittest.main(verbosity=2)
