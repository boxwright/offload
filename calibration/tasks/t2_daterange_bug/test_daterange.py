from datetime import date
from daterange import daterange, count_weekdays
def test_inclusive():
    assert list(daterange(date(2026,1,1), date(2026,1,3))) == [date(2026,1,1), date(2026,1,2), date(2026,1,3)]
def test_single_day():
    assert list(daterange(date(2026,1,1), date(2026,1,1))) == [date(2026,1,1)]
def test_reversed_empty():
    assert list(daterange(date(2026,1,3), date(2026,1,1))) == []
def test_step():
    assert list(daterange(date(2026,1,1), date(2026,1,10), 4)) == [date(2026,1,1), date(2026,1,5), date(2026,1,9)]
def test_weekdays():
    assert count_weekdays(date(2026,9,14), date(2026,9,20)) == 5  # Mon..Sun
def test_weekdays_partial():
    assert count_weekdays(date(2026,9,19), date(2026,9,21)) == 1  # Sat, Sun, Mon
