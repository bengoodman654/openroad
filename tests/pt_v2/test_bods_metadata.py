"""Synthetic metadata tests: zero published timetable acceptance."""
import unittest
from datetime import date
from bods_metadata import MetadataError, select, public_https_url, OPERATORS

def row(id=125, noc="TCVW", line="11", status="published", url="https://data.bus-data.dft.gov.uk/dataset/125.zip"):
    return dict(id=id,noc=[noc],lines=[line],status=status,url=url,name="Operator test service",operatorName="National Express Coventry",modified="2026-10-20T12:00:00Z",firstStartDate="2026-01-01",lastEndDate="2026-12-31")
class MetadataContractTests(unittest.TestCase):
    def test_codes_are_explicit_candidate_hypotheses(self):
        self.assertEqual(OPERATORS["COV-11"]["noc"],"TCVW")
        self.assertEqual(OPERATORS["BRI-75"]["noc"],"FBRI")
    def test_candidate_by_noc_line_and_published(self):
        x=select({"results":[row(),row(id=6,noc="FBRI"),row(id=7,line="12X"),row(id=8,status="inactive")]}, "TCVW","11",date(2026,10,24))
        self.assertEqual([a["dataset_id"] for a in x],[125])
    def test_casefold_noc_is_not_guessed(self):
        self.assertEqual(select({"results":[row(noc="XXXX")]}, "TCVW","11"),[])
    def test_missing_line_list_means_review_candidate(self):
        p=row();p.pop("lines");res=select({"results":[p]}, "TCVW","11")
        self.assertEqual(res[0]["line_metadata_match"],None)
    def test_untrusted_url_does_not_escape(self):
        for bad in ["http://example.org/data.zip","https://127.0.0.1/test.zip","https://localhost/x","https://10.0.0.1/file","https://evil.test/path?api_key=secret","file:///etc/passwd","https://user:pw@host.example/file"]:
            self.assertFalse(public_https_url(bad),bad)
        p=row(url="https://localhost/feed");res=select({"results":[p]},"TCVW","11")
        self.assertTrue(res[0]["manual_url_review_required"])
        self.assertIsNone(res[0]["download_url"])
    def test_public_https_accepted_without_query_token(self):
        self.assertTrue(public_https_url("https://data.bus-data.dft.gov.uk/a.zip"))
    def test_date_outside_metadata_range_is_not_selected(self):
        self.assertEqual(select({"results":[row()]},"TCVW","11",date(2027,5,1)),[])
    def test_untrusted_metadata_shape_blocked(self):
        with self.assertRaises(MetadataError):select({"results":None},"TCVW","11")
        with self.assertRaises(MetadataError):select({"results":[]},"11;DROP","11")
    def test_independent_operator_same_public_line_not_confused(self):
        x=select({"results":[row(id=1,noc="TCVW"),row(id=2,noc="FBRI")]},"TCVW","11")
        self.assertEqual([a["dataset_id"] for a in x],[1])

if __name__=="__main__":unittest.main()
