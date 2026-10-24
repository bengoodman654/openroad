"""Bounded TXC streaming safety regression checks."""
from io import BytesIO
import unittest
from txc_stream import scan,TXCStreamError

class TXCStreamContract(unittest.TestCase):
    def test_namespaced_txc_metadata_and_counts(self):
        xml=(b'<?xml version="1.0"?><TransXChange xmlns="urn:txc">'
             b'<Operators><Operator><NationalOperatorCode>TCVW</NationalOperatorCode></Operator></Operators>'
             b'<Services><Service><ServiceCode>PD0001111:11</ServiceCode>'
             b'<Lines><Line><LineName>11</LineName></Line><Line><LineName>12X</LineName></Line></Lines>'
             b'<JourneyPatterns><JourneyPattern/><JourneyPattern/></JourneyPatterns>'
             b'</Service></Services><VehicleJourneys><VehicleJourney/></VehicleJourneys></TransXChange>')
        s=scan(BytesIO(xml))
        self.assertEqual(s["lines"],["11","12X"])
        self.assertEqual(s["nocs"],["TCVW"])
        self.assertEqual(s["counts"]["VehicleJourney"],1)
        self.assertEqual(s["counts"]["JourneyPattern"],2)
    def test_refuses_dtd(self):
        with self.assertRaises(TXCStreamError):
            scan(BytesIO(b'<!DOCTYPE x [<!ENTITY y "a">]><x><LineName>&y;</LineName></x>'))
    def test_refuses_large_member(self):
        with self.assertRaises(TXCStreamError):
            scan(BytesIO(b'<root>'+b'a'*300+b'</root>'),limit=64)
    def test_rejects_malformed_xml(self):
        with self.assertRaises(Exception):
            scan(BytesIO(b'<TransXChange><LineName>11</LineName>'))
if __name__=="__main__":unittest.main()
