"""Target-list parser against messy, real-world inputs."""

import pytest
from astropy.coordinates import SkyCoord
import astropy.units as u

from artairmass.io.parser import parse_text, rows_to_targets, write_jskycalc

A1795 = SkyCoord("13h48m52.5s +26d35m34s")
PER = SkyCoord("03h19m48.16s +41d30m42.1s")
PHX = SkyCoord("23h44m43.9s -42d43m12s")
NEG0 = SkyCoord("10h00m00s -00d12m03s")


def rows(text, **kw):
    return parse_text(text, **kw).rows


def data(text, **kw):
    return [r for r in rows(text, **kw) if r.status != "comment"]


def sep(r, ref):
    return SkyCoord(r.ra * u.deg, r.dec * u.deg).separation(ref).arcsec


def check(r, ref, name=None, status=("ok",), tol=0.1):
    assert r.status in status, (r.status, r.messages, r.raw)
    assert sep(r, ref) < tol, (sep(r, ref), r.how, r.raw)
    if name is not None:
        assert r.name == name


# --------------------------------------------------------------------------- JSkyCalc formats
def test_jskycalc_space_format_with_url_and_comment():
    t = """# my list
4U1234+56   12 34 35.3  56 01 02   2000   file:///home/me/charts/4u1234.jpg
A1795       13 48 52.5  26 35 34   2000
"""
    r = data(t)
    assert len(r) == 2
    assert r[0].name == "4U1234+56" and r[0].url.startswith("file:///")
    check(r[1], A1795, "A1795")


def test_jskycalc_colon_and_1950():
    r = data("3C273   12:26:33.25   02:19:43.3   1950\n")[0]
    check(r, SkyCoord("12h29m06.70s +02d03m08.6s"), "3C273", tol=1.0)
    assert any("1950" in h for h in r.how)


def test_jskycalc_comma_format_with_decimal_degrees():
    t = """4U 1234+56, 12 34 35.3, 56 01 02, 1950, file:///x.jpg
A1795, 207.21875 d, 26.59278, 2000
"""
    r = data(t)
    assert r[0].name == "4U 1234+56"
    check(r[1], A1795, "A1795")


# --------------------------------------------------------------------------- headers / delimiters
def test_csv_with_header_and_extra_columns():
    t = "name,ra,dec,z,priority\nA1795,13:48:52.5,+26:35:34,0.0625,1\nPerseus,03:19:48.16,+41:30:42.1,0.0179,2\n"
    res = parse_text(t)
    r = [x for x in res.rows if x.status != "comment"]
    assert res.header and res.format.startswith("CSV")
    check(r[0], A1795, "A1795")
    check(r[1], PER, "Perseus")
    assert r[0].extra.get("col4") == "0.0625"   # unmapped column preserved
    assert r[0].notes == "1"                     # 'priority' maps to notes


def test_tsv_spreadsheet_export_degrees_header():
    t = "Target\tRA (deg)\tDec (deg)\nA1795\t207.21875\t26.59278\nPhoenix\t356.1829\t-42.72\n"
    r = data(t)
    check(r[0], A1795, "A1795")
    assert r[1].status == "ok"


def test_semicolon_european_csv():
    t = "Objet;RA;DEC\nA1795;13 48 52.5;+26 35 34\n"
    r = data(t)
    check(r[0], A1795, "A1795")


def test_header_degree_columns_small_values_not_ambiguous():
    t = "id,ra_deg,dec_deg\nX1,10.5,-30.0\nX2,12.25,-31.5\n"
    res = parse_text(t)
    assert res.ra_unit == "deg" and "header" in res.ra_unit_reason
    r = [x for x in res.rows if x.status != "comment"]
    assert r[0].status == "ok" and r[0].ra == pytest.approx(10.5, abs=1e-3)


def test_vizier_split_columns():
    t = "Name|RAh|RAm|RAs|DE-|DEd|DEm|DEs\nA1795|13|48|52.5|+|26|35|34\nPhx|23|44|43.9|-|42|43|12\n"
    r = data(t)
    check(r[0], A1795, "A1795")
    check(r[1], PHX, "Phx")


def test_ipac_table():
    t = r"""\ fixlen = T
\ RA = 'deg'
|   objname |        ra |      dec |
|      char |    double |   double |
     A1795    207.21875   26.59278
"""
    r = data(t)
    assert len(r) == 1
    check(r[0], A1795, "A1795")


def test_simbad_style_pipe_export():
    t = """ # | identifier |typ| coord1 (ICRS,J2000/2000) |
1|NGC  1275  |SyG|03 19 48.1597 +41 30 42.106|
"""
    r = data(t)
    ok = [x for x in r if x.status in ("ok", "warning")]
    assert ok and sep(ok[0], PER) < 1.0


# --------------------------------------------------------------------------- coordinate styles
@pytest.mark.parametrize("line", [
    "A1795 13:48:52.5 +26:35:34",
    "A1795 13 48 52.5 +26 35 34",
    "A1795 13h48m52.5s +26d35m34s",
    "A1795 13h 48m 52.5s +26d 35m 34s",
    "A1795 13h48m52.5s +26°35′34″",
    "A1795 207.21875d 26.59278",
    "A1795 207.21875 26.59278",
    "A1795\t13:48:52.5\t+26:35:34",
    "A1795   13:48:52.5   26:35:34   J2000",
    "A1795 13:48:52.5 26:35:34 2000.0 bright cluster, high priority",
])
def test_many_styles(line):
    r = data(line)[0]
    check(r, A1795, "A1795")


def test_name_with_spaces():
    r = data("Abell 1795 BCG   13:48:52.5  +26:35:34\n")[0]
    check(r, A1795, "Abell 1795 BCG")


def test_coordinates_first_then_name():
    r = data("13:48:52.5 +26:35:34 A1795\n")[0]
    check(r, A1795, "A1795")


def test_negative_zero_declination_keeps_sign():
    for line in ("t 10 00 00 -00 12 03", "t 10:00:00 -00:12:03", "t 10:00:00 −00:12:03"):
        check(data(line)[0], NEG0)


def test_unicode_and_crlf_and_bom():
    t = "﻿name,ra,dec\r\nA1795,13:48:52.5,−26:35:34\r\n"
    r = data(t)[0]
    assert r.dec < 0 and r.name == "A1795"


# --------------------------------------------------------------------------- ambiguity & errors
def test_decimal_ra_ambiguous_is_flagged_not_silent():
    t = "a 13.81458 26.59278\nb 3.3300 41.5117\n"
    res = parse_text(t)
    r = [x for x in res.rows if x.status != "comment"]
    assert res.ra_unit == "hours" and res.ra_unit_reason.startswith("AMBIGUOUS")
    assert all(x.status == "warning" for x in r)
    check(r[0], A1795, status=("warning",), tol=1.0)
    # user resolves the ambiguity → degrees, no warning
    res2 = parse_text(t, ra_unit="deg")
    assert all(x.status == "ok" for x in res2.rows if x.status != "comment")
    assert res2.rows[0].ra == pytest.approx(13.81458, abs=1e-3)


def test_decimal_ra_above_24_decides_degrees_for_whole_list():
    t = "a 207.21875 26.59278\nb 10.5 -30\n"
    res = parse_text(t)
    assert res.ra_unit == "deg"
    assert all(x.status == "ok" for x in res.rows)
    assert res.rows[1].ra == pytest.approx(10.5, abs=1e-3)


def test_errors_are_explained():
    t = "bad1 13:61:00 +26:00:00\nbad2 13:00:00 +95:00:00\nbad3 25:00:00 10 00 00\n"
    r = data(t)
    assert [x.status for x in r[:2]] == ["error", "error"]
    assert "60" in r[0].messages[0] and "90" in r[1].messages[0]


def test_name_only_rows_go_to_resolver():
    t = "NGC 1275\nAbell 1795\nM87\n"
    r = data(t)
    assert [x.status for x in r] == ["resolve"] * 3
    assert r[0].name == "NGC 1275"


def test_name_column_without_coords():
    r = data("name\nNGC 1275\nPKS 0745-191\n")
    assert [x.status for x in r] == ["resolve", "resolve"]
    assert r[1].name == "PKS 0745-191"


def test_duplicates_flagged():
    r = data("A 13:48:52.5 +26:35:34\nA 13:48:52.5 +26:35:34\n")
    assert r[1].status == "warning" and "duplicate" in r[1].messages[0]


def test_comments_and_blank_lines_ignored():
    t = "# header comment\n\n! another\n// c-style\nA1795 13:48:52.5 +26:35:34  # trailing note\n"
    r = data(t)
    assert len(r) == 1 and r[0].name == "A1795"


# --------------------------------------------------------------------------- other systems
def test_galactic_columns():
    t = "name,glon,glat\nGC,0.0,0.0\n"
    r = data(t)[0]
    assert r.status == "ok"
    assert SkyCoord(r.ra * u.deg, r.dec * u.deg).separation(SkyCoord("17h45m37.2s -28d56m10s")).arcsec < 2


def test_proper_motion_columns():
    t = "name,ra,dec,pmra,pmdec\nBarnard,269.452,4.6934,-801.551,10362.394\n"
    r = data(t)[0]
    assert r.pm_dec == pytest.approx(10362.394) and r.status == "ok"


def test_ds9_region_file():
    t = """# Region file format: DS9 version 4.1
global color=green
fk5
circle(207.21875,26.59278,30") # text={A1795}
circle(3:19:48.16,+41:30:42.1,30") # text={Perseus}
"""
    r = data(t)
    check(r[0], A1795, "A1795")
    check(r[1], PER, "Perseus")


def test_b1950_column_and_mixed_equinox():
    t = "name,ra,dec,equinox\n3C273,12:26:33.25,+02:19:43.3,B1950\nA1795,13:48:52.5,+26:35:34,J2000\n"
    r = data(t)
    check(r[0], SkyCoord("12h29m06.70s +02d03m08.6s"), tol=1.0)
    check(r[1], A1795)


# --------------------------------------------------------------------------- round trip
def test_roundtrip_jskycalc_export():
    targets = rows_to_targets([x.to_dict() for x in data("A1795 13:48:52.5 +26:35:34\nPerseus 3:19:48.16 41:30:42.1\n")])
    text = write_jskycalc(targets)
    back = data(text)
    check(back[0], A1795, "A1795")
    check(back[1], PER, "Perseus")


# --------------------------------------------------------------------------- traps found in practice
def test_numeric_name_tokens_do_not_steal_the_ra():
    r = data("3C 273 12:29:06.7 +02:03:08.6\n")[0]
    check(r, SkyCoord("12h29m06.7s +02d03m08.6s"), "3C 273")


def test_decimal_name_trap_is_flagged():
    r = data("NGC 300 13.72 -37.68\n", ra_unit="deg")[0]
    assert r.name == "NGC 300" and r.ra == pytest.approx(13.72, abs=1e-3)
    assert r.status == "warning" and "several readings" in r.messages[-1]


def test_iau_style_names_with_signs():
    t = "PKS 0745-191  07:47:31.3  -19:17:40\nSPT-CL J2344-4243  23:44:43.9  -42:43:12\n"
    r = data(t)
    assert r[0].name == "PKS 0745-191" and r[0].status == "ok"
    check(r[1], PHX, "SPT-CL J2344-4243")


def test_excel_quoted_csv_with_commas_in_fields():
    t = 'Name,RA,Dec,Comment\n"Abell 1795, BCG",13:48:52.5,+26:35:34,"cool core, strong AGN"\n'
    r = data(t)[0]
    check(r, A1795, "Abell 1795, BCG")
    assert r.notes == "cool core, strong AGN"


def test_index_column_and_trailing_whitespace():
    t = "1  A1795  13:48:52.5  +26:35:34   \n2  Perseus  03:19:48.16  +41:30:42.1\t\n"
    r = data(t)
    assert r[0].name == "1 A1795" or r[0].name == "A1795" or r[0].name.endswith("A1795")
    check(r[1], PER)


def test_ned_style_export():
    t = "No.|Object Name|RA(deg)|DEC(deg)|Type|Velocity\n1|NGC 1275|49.95067|41.51170|G|5264\n"
    r = data(t)[0]
    assert r.name == "NGC 1275" and r.status == "ok"
    assert sep(r, PER) < 1.0


def test_mixed_jskycalc_space_and_comma_lines():
    t = "A1795 13 48 52.5 26 35 34 2000\nPerseus, 03:19:48.16, +41:30:42.1, 2000\n"
    r = data(t)
    check(r[0], A1795, "A1795")
    check(r[1], PER, "Perseus")


def test_hms_decimal_hours_token():
    r = data("A1795 13.814583h 26.592778\n")[0]
    check(r, A1795, "A1795", tol=0.5)


def test_header_line_in_mixed_free_form_list():
    t = "name, ra, dec, z\nAbell 1795, 13:48:52.5, +26:35:34, 0.0625\nPerseus 03 19 48.16 +41 30 42.1\n"
    r = data(t)
    assert len(r) == 2
    check(r[0], A1795, "Abell 1795")
    check(r[1], PER, "Perseus")


def test_error_row_keeps_offending_text_for_inline_fixing():
    r = data("Typo cl.   13:61:00  +26:00:00\n")[0]
    assert r.status == "error" and r.name == "Typo cl."
    assert r.ra_text == "13:61:00" and r.dec_text == "+26:00:00"
