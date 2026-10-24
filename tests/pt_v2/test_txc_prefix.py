"""The TXC head-scanner must recognise service names without expanding large XML files."""
import unittest
from inspect_txc_20442 import prefix_labels

class BoundedTransXChangeDiscovery(unittest.TestCase):
    def test_namespaced_lines_and_operator(self):
        raw=(b'<tx:TransXChange xmlns:tx="urn:txc"><tx:Operators>'
             b'<tx:NationalOperatorCode>TCVW</tx:NationalOperatorCode></tx:Operators>'
             b'<tx:Lines><tx:Line><tx:LineName>11</tx:LineName></tx:Line>'
             b'<tx:Line><tx:LineName>12X</tx:LineName></tx:Line>'
             b'</tx:Lines></tx:TransXChange>')
        lines,ops=prefix_labels(raw)
        self.assertEqual(lines,{"11","12X"})
        self.assertEqual(ops,{"TCVW"})
    def test_partial_prefix_is_an_inspection_not_full_parse(self):
        raw=b'<TransXChange><Lines><Line><LineName>9</LineName></Line>'
        lines,ops=prefix_labels(raw)
        self.assertIn("9",lines)
        self.assertEqual(ops,set())
    def test_dtd_entity_payload_is_not_parsed(self):
        raw=b'<!DOCTYPE x [<!ENTITY bad "11">]><x><LineName>&bad;</LineName></x>'
        self.assertEqual(prefix_labels(raw),(set(),set()))

if __name__=="__main__":unittest.main()
