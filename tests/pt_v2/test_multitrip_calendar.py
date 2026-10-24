"""Offline unit tests of the multi-trip calendar selection and strict rejection model."""
import unittest
from datetime import date
from xml.etree import ElementTree as ET
from coventry_11_multitrip import operating_day,revision,span,seconds,UnsupportedTXC

def prof(tokens,extra=""):
    days="".join(f"<{token}/>" for token in tokens)
    return ET.fromstring("<OperatingProfile><RegularDayType><DaysOfWeek>"+days+
        "</DaysOfWeek></RegularDayType><BankHolidayOperation>"+
        "<DaysOfNonOperation><ChristmasDay/></DaysOfNonOperation></BankHolidayOperation>"+
        extra+"</OperatingProfile>")

class MultiTripCalendarContracts(unittest.TestCase):
    def test_saturday_and_sunday_are_supported_explicitly(self):
        self.assertTrue(operating_day(prof(["Saturday"]),date(2026,10,24),True))
        self.assertFalse(operating_day(prof(["Saturday"]),date(2026,10,23),True))
        self.assertTrue(operating_day(prof(["Sunday"]),date(2026,10,25),True))

    def test_weekday_groups_and_friday_only(self):
        self.assertTrue(operating_day(prof(["Monday","Tuesday","Wednesday","Thursday","Friday"]),date(2026,10,23),True))
        self.assertTrue(operating_day(prof(["MondayToFriday"]),date(2026,10,26),True))
        self.assertFalse(operating_day(prof(["MondayToFriday"]),date(2026,10,24),True))

    def test_bank_holiday_status_must_be_proved(self):
        self.assertIsNone(operating_day(prof(["Friday"]),date(2026,10,23)))
        self.assertTrue(operating_day(prof(["Friday"]),date(2026,10,23),True))

    def test_special_days_and_unknown_school_rules_fail_closed(self):
        a=prof(["Friday"],"<SpecialDaysOperation><DaysOfOperation><Schooldays/></DaysOfOperation></SpecialDaysOperation>")
        self.assertIsNone(operating_day(a,date(2026,10,23),True))
        self.assertIsNone(operating_day(prof(["Schooldays"]),date(2026,10,23),True))

    def test_invalid_time_and_duration_are_blocked(self):
        for s in ["","8:45","-02:00:00","12:66:00"]:
            with self.assertRaises(UnsupportedTXC):seconds(s)
        with self.assertRaises(UnsupportedTXC):span("P12Y")
        self.assertEqual(span("PT2M30S"),150)
        self.assertEqual(seconds("25:00:00"),90000)

    def test_revision_is_explicit_not_implicit_future_fallback(self):
        self.assertIn("20260920",revision(date(2026,10,23)))
        self.assertIn("20260920",revision(date(2026,10,24)))
        self.assertIn("20261025",revision(date(2026,10,25)))
        self.assertIn("20261025",revision(date(2026,10,26)))
        with self.assertRaises(UnsupportedTXC):revision(date(2026,11,1))

if __name__=="__main__":unittest.main()
