from datetime import date, datetime

import pytest

from artairmass.core import timeutil as tu


@pytest.mark.parametrize("text,days", [
    ("1 h", 1 / 24), ("1h", 1 / 24), ("-30m", -30 / 1440), ("2", 2 / 24), ("1 d", 1.0),
    ("10 s", 10 / 86400), ("1 t", tu.SIDEREAL_DAY_D), ("1 l", tu.SYNODIC_MONTH_D),
    ("1.5 hr", 1.5 / 24), ("3 days", 3.0),
])
def test_parse_step(text, days):
    assert tu.parse_step(text) == pytest.approx(days)


@pytest.mark.parametrize("bad", ["", "h", "1 q", "abc"])
def test_parse_step_rejects(bad):
    with pytest.raises(ValueError):
        tu.parse_step(bad)


def test_local_roundtrip_and_dst_chile():
    tz = "America/Santiago"
    # Chile 2026: DST ends Sun Apr 5 (00:00 → Sat 23:00), starts Sun Sep 6 (00:00 → 01:00)
    before = tu.local_to_time(datetime(2026, 4, 4, 21, 0), tz)
    after = tu.local_to_time(datetime(2026, 4, 5, 21, 0), tz)
    assert tu.utc_offset_hours(before, tz) == -3
    assert tu.utc_offset_hours(after, tz) == -4
    t = tu.local_to_time(datetime(2026, 9, 6, 0, 30), tz)  # inside the gap
    assert tu.to_local(t, tz).hour == 1


def test_night_window_spans_dst_change():
    a, b = tu.night_window(date(2026, 3, 7), "America/Los_Angeles")  # DST starts Mar 8
    assert (b.jd - a.jd) * 24 == pytest.approx(23.0)
    a, b = tu.night_window(date(2026, 10, 31), "America/Los_Angeles")  # DST ends Nov 1
    assert (b.jd - a.jd) * 24 == pytest.approx(25.0)


def test_night_of_noon_rule():
    tz = "America/Santiago"
    assert tu.night_of(tu.local_to_time(datetime(2026, 10, 8, 2, 0), tz), tz) == date(2026, 10, 7)
    assert tu.night_of(tu.local_to_time(datetime(2026, 10, 8, 13, 0), tz), tz) == date(2026, 10, 8)


def test_format_hms_carry():
    assert tu.format_hms(1.9999999) == "02:00:00"
    assert tu.format_hms(-0.5, signed=True) == "-00:30:00"
    assert tu.format_hms(12.5, decimals=1) == "12:30:00.0"
