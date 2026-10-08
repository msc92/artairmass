from datetime import date

import numpy as np
import pytest

from artairmass.core.besttime import best_time, describe, semester_of
from artairmass.core.sites import get_site
from artairmass.core.targets import Target


@pytest.fixture(scope="module")
def lco_year():
    T = [Target("A1795", 207.2187, 26.5928), Target("Phoenix", 356.18, -42.72), Target("Perseus", 49.95, 41.51)]
    return best_time(get_site("lco"), T, date(2027, 1, 1), 365)


def test_semesters():
    assert semester_of(date(2027, 2, 1)) == "2027A" and semester_of(date(2027, 7, 31)) == "2027A"
    assert semester_of(date(2027, 8, 1)) == "2027B" and semester_of(date(2028, 1, 31)) == "2027B"
    assert semester_of(date(2027, 1, 15)) == "2026B"


def test_midnight_transit_dates(lco_year):
    a1795, phx, _ = lco_year["targets"]
    # local clock midnight in Chile (UTC-4/-3) lags solar midnight → late April / mid October
    assert a1795["midnight_transit"] == "2027-04-29"
    assert phx["midnight_transit"][:7] == "2027-10"


def test_hours_and_language(lco_year):
    a1795, phx, per = lco_year["targets"]
    assert per["peak_hours"] < 0.25 and "Not observable" in per["summary"]
    assert phx["recommended_type"] == "B" and phx["recommended_semester"] == "2027B" and "Sep" in phx["summary"]
    assert "May" in phx["observable_ranges"][0][0] or phx["observable_ranges"][0][0] < "2027-06-01"
    assert a1795["recommended_type"] == "A" and a1795["recommended_semester"] == "2027A"
    # hours can never exceed the dark time available that night
    dark = np.array(lco_year["dark_hours"])
    for t in lco_year["targets"]:
        assert np.all(np.array(t["hours"]) <= dark + 1e-6)
    assert len(lco_year["monthly"]["months"]) == 12


def test_moon_constraints_only_remove_time():
    s = get_site("paranal")
    T = [Target("Phoenix", 356.18, -42.72)]
    free = best_time(s, T, date(2027, 1, 1), 120, moon="bright")["targets"][0]
    dark = best_time(s, T, date(2027, 1, 1), 120, moon="dark", min_sep=30)["targets"][0]
    assert np.all(np.array(dark["hours"]) <= np.array(free["hours"]) + 1e-9)
    assert sum(dark["hours"]) < sum(free["hours"])


def test_matches_single_night_engine():
    """Year engine vs the per-night tracks engine for one night (10-min vs 2-min sampling)."""
    from artairmass.core.night import plan_night, summarize
    site = get_site("lco")
    tg = [Target("Phoenix", 356.18, -42.72)]
    yr = best_time(site, tg, date(2026, 10, 7), 3, limit=2.0)
    n, tr = plan_night(site, date(2026, 10, 7), tg)
    s = summarize(n, tr, tg, 2.0)
    assert yr["targets"][0]["hours"][0] == pytest.approx(s[0]["dark_hours"], abs=0.2)


def test_wraparound_description():
    dates = [date(2027, 1, 1) + __import__("datetime").timedelta(days=k) for k in range(365)]
    h = np.where((np.arange(365) > 120) | (np.arange(365) < 10), 5.0, 0.0)
    d = describe(dates, h, dates[0])
    assert "early Jan" in d["summary"] or "May to" in d["summary"]
    assert "around" not in d["summary"].split("Usefully")[1]


def test_next_semester():
    from artairmass.core.besttime import next_semester
    assert next_semester(date(2026, 10, 1), "A") == "2027A"
    assert next_semester(date(2026, 10, 1), "B") == "2027B"
    assert next_semester(date(2027, 1, 1), "B") == "2027B"
    assert next_semester(date(2026, 8, 1), "B") == "2026B"
