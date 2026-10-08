"""Flexible target-list parser.

Accepts what people actually paste: CSV / TSV / semicolon / pipe (IPAC) / whitespace,
optional header rows (columns found by name), ``#`` comments, extra columns, names with
spaces, sexagesimal with colons / spaces / h-m-s & d-m-s letters, decimal degrees or hours,
per-row equinox, proper motions, galactic l/b, URLs (JSkyCalc), ds9 region files, and
name-only rows (to be resolved with Sesame).

Every input line yields a ``Row`` with a status:

* ``ok``         parsed unambiguously
* ``warning``    parsed, but with an assumption the user should confirm (e.g. decimal RA ≤ 24
                 read as hours, duplicate name) — shown, never silent
* ``resolve``    no coordinates: a name to look up
* ``error``      could not be parsed (message says why)
* ``comment``    comment / blank / header (kept for line numbering)

Nothing here guesses silently: every interpretation is recorded in ``Row.how``.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import asdict, dataclass, field

from ..core.targets import galactic_to_icrs, parse_equinox, to_icrs
from .coords import _UNICODE, CoordError, parse_dec, parse_ra

# ----------------------------------------------------------------------------- columns
SYNONYMS = {
    "name": ["name", "object", "objname", "obj", "target", "targetname", "target_name", "id", "source", "src",
             "main_id", "identifier", "field", "cluster", "galaxy", "star", "designation", "label",
             "objet", "nom", "objeto", "nombre", "objekt"],
    "radec": ["coord1", "coords", "coordinates", "coord", "position", "radec", "ra_dec", "pos"],
    "ra": ["ra", "raj2000", "ra_j2000", "ra2000", "ra_2000", "ra_icrs", "alpha", "alpha_j2000", "_raj2000",
           "ra_deg", "radeg", "ra_hms", "ra_hours", "rah_decimal", "right_ascension", "ra_d", "ra(j2000)", "ra_obj",
           "racen", "ra_center", "ra_targ"],
    "dec": ["dec", "decl", "dej2000", "dec_j2000", "dec2000", "dec_2000", "de_icrs", "dec_icrs", "delta",
            "delta_j2000", "_dej2000", "dec_deg", "decdeg", "dec_dms", "declination", "de", "dec_d", "dec(j2000)",
            "dec_obj", "deccen", "dec_center", "dec_targ"],
    "equinox": ["equinox", "epoch", "eq", "equ", "coord_epoch", "equinox_year"],
    "pm_ra": ["pmra", "pm_ra", "pmra_cosdec", "pm_ra_cosdec", "pmalpha", "mu_ra", "pmrac"],
    "pm_dec": ["pmdec", "pm_dec", "pmde", "pmdelta", "mu_dec"],
    "glon": ["glon", "gal_l", "lii", "l", "gl", "galactic_l", "l_deg"],
    "glat": ["glat", "gal_b", "bii", "b", "gb", "galactic_b", "b_deg"],
    "url": ["url", "link", "finder", "chart", "finding_chart", "web"],
    "notes": ["notes", "note", "comment", "comments", "remarks", "remark", "description", "desc", "priority"],
    "rah": ["rah", "ra_h"], "ram": ["ram", "ra_m"], "ras": ["ras", "ra_s"],
    "ded": ["ded", "decd", "de_d", "dec_d_int"], "dem": ["dem", "decm", "de_m"], "des": ["des", "decs", "de_s"],
    "design": ["de-", "dec_sign", "de_sign", "sign"],
}
_LOOKUP = {s: k for k, vs in SYNONYMS.items() for s in vs}


def _norm_header(h: str) -> tuple[str, str | None]:
    """Header cell → (canonical key or '', unit hint 'deg'|'hours'|None)."""
    raw = h.strip().strip('"\'').strip()
    low = raw.lower()
    unit = None
    if re.search(r"\b(deg|degrees?|°)\b|_deg\b|deg\)", low) or low.endswith("deg"):
        unit = "deg"
    elif re.search(r"\(h\)|\bhours?\b|_hours?\b|\bhms\b|_hms\b|\(hms\)", low):
        unit = "hours"
    base = re.sub(r"\s*[\[(].*?[\])]\s*", "", low)  # drop "(deg)", "[J2000]"
    base = re.sub(r"[\s.]+", "_", base).strip("_")
    if base in _LOOKUP:
        return _LOOKUP[base], unit
    base2 = re.sub(r"_?(deg|hms|dms|hours?)$", "", base)
    if base2 in _LOOKUP:
        return _LOOKUP[base2], unit
    if low.strip() in _LOOKUP:
        return _LOOKUP[low.strip()], unit
    return "", unit


# ----------------------------------------------------------------------------- results
@dataclass
class Row:
    line: int
    raw: str
    status: str = "ok"
    name: str = ""
    ra: float | None = None          # ICRS deg
    dec: float | None = None
    ra_text: str = ""
    dec_text: str = ""
    equinox: str = "2000"
    pm_ra_cosdec: float = 0.0
    pm_dec: float = 0.0
    url: str = ""
    notes: str = ""
    how: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    decimal_ra: bool = False         # RA was a bare decimal (unit decided at list level)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseResult:
    rows: list[Row]
    delimiter: str
    header: list[str] | None
    columns: dict
    ra_unit: str                      # what decimal RAs were taken as
    ra_unit_reason: str
    format: str

    def to_dict(self) -> dict:
        counts = {}
        for r in self.rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {"rows": [r.to_dict() for r in self.rows if r.status != "comment"],
                "delimiter": self.delimiter, "header": self.header, "columns": self.columns,
                "ra_unit": self.ra_unit, "ra_unit_reason": self.ra_unit_reason,
                "format": self.format, "counts": counts}


# ----------------------------------------------------------------------------- helpers
_COMMENT = re.compile(r"^\s*(#|!|//|%)")
_URL = re.compile(r"^(https?://|file:|ftp://|www\.)", re.I)
_EQUINOX_TOKEN = re.compile(r"^(?:[JB]\s*)?(1[89]\d\d|20\d\d)(?:\.\d+)?$|^(ICRS|FK5|FK4|J2000|B1950|DATE)$", re.I)
_DECIMAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")
_SEXA_TOKEN = re.compile(r"^[+-]?\d{1,3}(:\d{1,2}(:\d{1,2}(\.\d*)?)?|[hd°]\s*\d{1,2}[m']\s*(\d{1,2}(\.\d*)?[s\"]?)?)$", re.I)


def _is_number(tok: str) -> bool:
    return bool(_DECIMAL.match(tok))


def _cells_have_coords(cells: list[str]) -> bool:
    for j in range(len(cells) - 1):
        try:
            parse_ra(cells[j])
            parse_dec(cells[j + 1])
            return True
        except CoordError:
            pass
    return any(_combined_cell(c) for c in cells)


def _combined_cell(cell: str):
    """A single cell holding both RA and Dec (e.g. SIMBAD's 'coord1')."""
    toks = cell.split()
    if len(toks) < 2:
        return None
    hit = _find_coords(toks)
    return hit if hit and hit[0] == 0 and hit[1] == len(toks) and not hit[4] else None


def _detect_delimiter(lines: list[str]) -> str:
    """Choose the delimiter under which the most lines yield an RA/Dec pair; fall back to
    the most consistent separator (name-only lists), then whitespace."""
    data = [ln for ln in lines if ln.strip() and not _COMMENT.match(ln)][:40]
    if not data:
        return "whitespace"
    scores = {}
    for d in ("\t", ",", ";", "|", "whitespace"):
        if d != "whitespace" and sum(d in ln for ln in data) < 0.8 * len(data):
            continue
        ok = 0
        for ln in data:
            cells = _split(ln, d)
            ok += bool(_find_coords(cells)) if d == "whitespace" else _cells_have_coords(cells)
        scores[d] = ok
    best = max(scores.values())
    if best > 0:
        for d in ("\t", ",", ";", "|", "whitespace"):  # preference order on ties
            if scores.get(d) == best:
                return d
    for d in ("\t", ",", ";", "|"):
        if d in scores:
            return d
    return "whitespace"


def _split(line: str, delim: str) -> list[str]:
    if delim == "whitespace":
        return line.split()
    if delim == "|":
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        return cells
    return [c.strip() for c in next(csv.reader([line], delimiter=delim, skipinitialspace=True))]


# ----------------------------------------------------------------------------- ds9 regions
_DS9 = re.compile(r"^\s*(?:fk5|icrs|j2000|fk4|b1950|galactic)?\s*;?\s*(circle|point|box|ellipse|polygon|text|annulus)\s*\(\s*([^,)]+)\s*,\s*([^,)]+)", re.I)


def _parse_ds9(lines: list[str]) -> list[Row] | None:
    if not any(re.match(r"^\s*(# Region file format|global |fk5|icrs|image|physical)", ln, re.I) for ln in lines[:5]):
        return None
    frame = "fk5"
    rows = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        low = s.lower()
        if low in ("fk5", "icrs", "j2000", "fk4", "b1950", "galactic", "image", "physical"):
            frame = low
            rows.append(Row(line=i, raw=ln, status="comment"))
            continue
        m = _DS9.match(s)
        if not m:
            rows.append(Row(line=i, raw=ln, status="comment"))
            continue
        name = ""
        tm = re.search(r"text\s*=\s*[{\"']([^}\"']*)[}\"']", s)
        if tm:
            name = tm.group(1).strip()
        r = Row(line=i, raw=ln, name=name or f"region {i}", ra_text=m.group(2), dec_text=m.group(3))
        if frame in ("image", "physical"):
            r.status, r.messages = "error", ["image/physical region coordinates can't be converted"]
        elif frame == "galactic":
            _apply_galactic(r, m.group(2), m.group(3))
        else:
            r.equinox = {"fk4": "B1950", "b1950": "B1950", "icrs": "ICRS"}.get(frame, "2000")
            _apply_radec(r, m.group(2), m.group(3), ra_unit="deg" if _is_number(m.group(2)) else "auto")
        rows.append(r)
    return rows


# ----------------------------------------------------------------------------- core
def _apply_radec(row: Row, ra_txt: str, dec_txt: str, ra_unit: str = "auto", when=None) -> None:
    row.ra_text, row.dec_text = ra_txt.strip(), dec_txt.strip()
    try:
        pra = parse_ra(row.ra_text, ra_unit)
        pdec = parse_dec(row.dec_text)
    except CoordError as e:
        row.status = "error"
        row.messages.append(str(e))
        return
    row.decimal_ra = _is_number(row.ra_text.strip()) and ra_unit == "auto"
    row.how.append(f"RA: {pra.how}")
    row.how.append(f"Dec: {pdec.how}")
    try:
        frame, _ = parse_equinox(row.equinox)
        row.ra, row.dec = to_icrs(pra.deg, pdec.deg, row.equinox, when=when)
        if frame != "fk5" or str(row.equinox).strip() not in ("2000", "2000.0", "J2000", "J2000.0"):
            row.how.append(f"equinox {row.equinox} → ICRS")
    except ValueError as e:
        row.status = "error"
        row.messages.append(str(e))


def _apply_galactic(row: Row, l_txt: str, b_txt: str) -> None:
    try:
        lv, bv = float(l_txt), float(b_txt)
        if not -90 <= bv <= 90:
            raise ValueError(f"galactic b {bv} out of range")
        row.ra, row.dec = galactic_to_icrs(lv % 360, bv)
        row.ra_text, row.dec_text = f"l={lv}", f"b={bv}"
        row.how.append("galactic l, b → ICRS")
    except ValueError as e:
        row.status = "error"
        row.messages.append(str(e))


def _is_sexa(tok: str, kind: str) -> bool:
    if kind == "ra":
        return bool(_SEXA_TOKEN.match(tok) or re.fullmatch(r"\d{1,2}h\d{1,2}m[\d.]*s?", tok, re.I))
    return bool(_SEXA_TOKEN.match(tok) or re.fullmatch(r"[+-]?\d{1,2}d\d{1,2}m[\d.]*s?", tok, re.I))


def _pair_ok(a: str, b: str) -> bool:
    try:
        parse_ra(a)
        parse_dec(b)
        return True
    except CoordError:
        return False


def _find_coords(tokens: list[str]):
    """Locate an RA/Dec pair in whitespace tokens → (start, end, ra_text, dec_text, ambiguous).

    Pass 1 (unambiguous forms) wins: hh:mm:ss / letter forms, and JSkyCalc's 3+3 integer
    groups. Pass 2 considers bare decimals; when more than one placement is plausible
    (e.g. "NGC 300 13.72 -37.68") the best-scoring one is used and flagged ambiguous.
    """
    n = len(tokens)
    for i in range(n):
        if i + 2 <= n and _is_sexa(tokens[i], "ra") and _is_sexa(tokens[i + 1], "dec") and _pair_ok(tokens[i], tokens[i + 1]):
            return i, i + 2, tokens[i], tokens[i + 1], False
        if i + 6 <= n and re.fullmatch(r"\d+h", tokens[i], re.I) and re.fullmatch(r"[+-]?\d+[d°]", tokens[i + 3], re.I):
            return i, i + 6, " ".join(tokens[i:i + 3]), " ".join(tokens[i + 3:i + 6]), False
        if i + 6 <= n and all(re.fullmatch(r"[+-]?\d+(\.\d*)?", t) for t in tokens[i:i + 6]) \
                and "." not in tokens[i] + tokens[i + 1] + tokens[i + 3] + tokens[i + 4]:
            ra, dec = " ".join(tokens[i:i + 3]), " ".join(tokens[i + 3:i + 6])
            if float(tokens[i]) < 24 and _pair_ok(ra, dec):
                return i, i + 6, ra, dec, False
    # hh mm  dd mm at the end of the line
    if n >= 5 and all(re.fullmatch(r"[+-]?\d+", t) for t in tokens[-4:]):
        ra, dec = " ".join(tokens[-4:-2]), " ".join(tokens[-2:])
        if float(tokens[-4]) < 24 and _pair_ok(ra, dec):
            return n - 4, n, ra, dec, False

    def dec_tok(t, kind):
        return _is_number(t) or re.fullmatch(r"[+-]?\d+(\.\d*)?[d°]" if kind == "dec" else r"\d+(\.\d*)?[dh°]", t, re.I)

    cands = []
    for i in range(n - 1):
        a, b = tokens[i], tokens[i + 1]
        if dec_tok(a, "ra") and dec_tok(b, "dec") and _pair_ok(a, b):
            name, rest = tokens[:i], [t for t in tokens[i + 2:] if not _EQUINOX_TOKEN.match(t) and not _URL.match(t)]
            score = 0
            score += 2 if name and not (_is_number(name[-1]) and "." in name[-1]) else 0  # catalogue numbers are integers
            score -= 2 * sum(1 for t in name if _is_number(t) and "." in t)
            score -= sum(1 for t in rest if _is_number(t))
            score += 1 if not name and rest and not _is_number(rest[0]) else 0  # coords first, name after
            cands.append((score, -i, i))
    if not cands:
        return None
    cands.sort(reverse=True)
    best = cands[0][2]
    ambiguous = len(cands) > 1 and cands[1][0] == cands[0][0]
    if not ambiguous and len(cands) > 1 and any(_is_number(t) for t in tokens[:best]):
        ambiguous = True  # a numeric token in the name could have been the RA
    return best, best + 2, tokens[best], tokens[best + 1], ambiguous


_COORDLIKE = re.compile(r"^[+-]?\d{1,3}(:\d|[hd°]\d)", re.I)


def _coord_error(tokens: list[str]) -> str | None:
    """If the line contains coordinate-looking tokens that failed to parse, say why."""
    idx = [k for k, t in enumerate(tokens) if _COORDLIKE.match(t)]
    if not idx:
        return None
    k = idx[0]
    try:
        parse_ra(tokens[k])
    except CoordError as e:
        return f"RA: {e}"
    if k + 1 < len(tokens):
        try:
            parse_dec(tokens[k + 1])
        except CoordError as e:
            return f"Dec: {e}"
    return f"couldn't read coordinates near {tokens[k]!r}"


def _parse_free_line(row: Row, tokens: list[str], ra_unit: str, default_equinox: str, when) -> None:
    hit = _find_coords(tokens)
    if hit is not None and any(_COORDLIKE.match(t) for t in tokens[:hit[0]]):
        hit = None  # a coordinate-looking token sits in the "name": something upstream failed
    if hit is None:
        err = _coord_error(tokens)
        urls = [t for t in tokens if _URL.match(t)]
        if urls:
            row.url = urls[0]
        name = " ".join(t for t in tokens if not _URL.match(t)).strip()
        if err:
            k = next(j for j, t in enumerate(tokens) if _COORDLIKE.match(t))
            row.name = " ".join(tokens[:k]) or f"target {row.line}"
            row.ra_text = tokens[k]
            row.dec_text = tokens[k + 1] if k + 1 < len(tokens) else ""
            row.status = "error"
            row.messages.append(err)
        elif name:
            row.name, row.status = name, "resolve"
            row.messages.append("no coordinates — will look up the name")
        else:
            row.status = "error"
            row.messages.append("couldn't find an RA/Dec pair in this line")
        return
    start, end, ra_t, dec_t, ambiguous = hit
    before, after = tokens[:start], tokens[end:]
    rest = []
    row.equinox = default_equinox
    for t in after:
        if _URL.match(t) and not row.url:
            row.url = t
        elif _EQUINOX_TOKEN.match(t) and row.equinox == default_equinox and not rest:
            row.equinox = t
        else:
            rest.append(t)
    name = " ".join(before).strip()
    if not name and rest:  # coordinates first, name after
        name, rest = " ".join(rest), []
    row.name = name or f"target {row.line}"
    if rest:
        row.notes = " ".join(rest)
    _apply_radec(row, ra_t, dec_t, ra_unit, when)
    if ambiguous and row.status == "ok":
        row.status = "warning"
        row.messages.append(f"several readings possible — took RA={ra_t}, Dec={dec_t}, name “{row.name}”; "
                            "use colons/hms or a delimiter to be explicit")


def parse_text(text: str, ra_unit: str = "auto", default_equinox: str = "2000",
               delimiter: str = "auto", header: str = "auto", coord_system: str = "auto",
               when=None) -> ParseResult:
    """Parse a pasted/uploaded list. Options mirror the UI's controls."""
    text = text.lstrip("\ufeff").translate(_UNICODE)
    lines = text.splitlines()

    ipac = _parse_ipac(lines, ra_unit, default_equinox, coord_system, when)
    if ipac is not None:
        return ipac

    ds9 = _parse_ds9(lines)
    if ds9 is not None:
        rows = ds9
        _finalize(rows, ra_unit)
        return ParseResult(rows, "ds9", None, {}, ra_unit, "ds9 region file", "ds9 regions")

    delim = _detect_delimiter(lines) if delimiter == "auto" else delimiter
    rows: list[Row] = []
    hdr: list[str] | None = None
    colmap: dict[str, int] = {}
    units: dict[str, str] = {}
    fmt = {"whitespace": "whitespace-separated", ",": "CSV", "\t": "TSV", ";": "semicolon-separated", "|": "pipe-separated (IPAC-like)"}.get(delim, delim)

    for i, ln in enumerate(lines, 1):
        if not ln.strip() or _COMMENT.match(ln) or (delim == "|" and re.match(r"^\s*\\", ln)):
            rows.append(Row(line=i, raw=ln, status="comment"))
            continue
        cells = _split(ln, delim)
        if hdr is None and header != "no" and not colmap:
            mapped = [_norm_header(c) for c in cells]
            keys = [k for k, _ in mapped if k]
            looks_header = (("ra" in keys and "dec" in keys) or ("glon" in keys and "glat" in keys)
                            or ("rah" in keys and "ded" in keys) or ("name" in keys and len(cells) == 1)
                            or ("name" in keys and not _find_coords(cells)))
            if header == "yes" or (looks_header and not _find_coords(cells)):
                hdr = cells
                for j, (k, unit) in enumerate(mapped):
                    if k and k not in colmap:
                        colmap[k] = j
                        if unit:
                            units[k] = unit
                rows.append(Row(line=i, raw=ln, status="comment"))
                continue
        if hdr is None and not colmap and delim == "whitespace" and header != "no" and "," in ln:
            mk = [_norm_header(c)[0] for c in _split(ln, ",")]
            if "ra" in mk and "dec" in mk and not _cells_have_coords(_split(ln, ",")):
                rows.append(Row(line=i, raw=ln, status="comment"))  # header of a mixed list
                continue
        if delim == "|" and set(ln.strip()) <= set("|-+= "):
            rows.append(Row(line=i, raw=ln, status="comment"))
            continue
        row = Row(line=i, raw=ln, equinox=default_equinox)
        if colmap and hdr is not None and len(hdr) == 1:
            cells = [ln.strip()]  # a single named column: the whole line is the value
        if colmap:
            _parse_mapped(row, cells, colmap, units, ra_unit, default_equinox, coord_system, when)
        elif delim == "whitespace" and "," in ln and _cells_have_coords(_split(ln, ",")):
            # JSkyCalc lists may mix space- and comma-separated lines
            _parse_delimited_noheader(row, _split(ln, ","), ra_unit, default_equinox, coord_system, when)
        elif delim == "whitespace":
            _parse_free_line(row, _strip_trailing_comment(ln).split(), ra_unit, default_equinox, when)
        else:
            _parse_delimited_noheader(row, cells, ra_unit, default_equinox, coord_system, when)
        rows.append(row)

    decided, reason = _finalize(rows, ra_unit, units.get("ra"), when)
    columns = {k: (hdr[j] if hdr else j) for k, j in colmap.items()}
    return ParseResult(rows, delim, hdr, columns, decided, reason, fmt + (" with header" if hdr else ""))


def _strip_trailing_comment(ln: str) -> str:
    return re.split(r"\s#\s|\s#$", ln, maxsplit=1)[0]


def _parse_ipac(lines, ra_unit, default_equinox, coord_system, when) -> ParseResult | None:
    """IPAC table: '\\' keywords, then '|name|type|unit|' header lines, then fixed-width data."""
    head = [ln for ln in lines if ln.strip()][:3]
    if not head or not (head[0].lstrip().startswith("\\") or
                        (head[0].lstrip().startswith("|") and len(head) > 1 and head[1].lstrip().startswith("|")
                         and not any(ch.isdigit() for ch in head[1].replace("|", "")[:40]))):
        return None
    bars = None
    names: list[str] = []
    rows: list[Row] = []
    data_lines = []
    for i, ln in enumerate(lines, 1):
        st = ln.strip()
        if not st or st.startswith("\\"):
            rows.append(Row(line=i, raw=ln, status="comment"))
        elif st.startswith("|"):
            if bars is None:
                bars = [k for k, ch in enumerate(ln) if ch == "|"]
                names = [ln[a + 1:b].strip() for a, b in zip(bars, bars[1:])]
            rows.append(Row(line=i, raw=ln, status="comment"))
        else:
            data_lines.append((i, ln))
    if bars is None:
        return None
    # rebuild as TSV and reuse the header machinery
    tsv = ["\t".join(names)]
    for _, ln in data_lines:
        tsv.append("\t".join(ln[a + 1:b].strip() if a + 1 < len(ln) else "" for a, b in zip(bars, bars[1:])))
    res = parse_text("\n".join(tsv), ra_unit, default_equinox, "\t", "yes", coord_system, when)
    body = [r for r in res.rows if r.status != "comment"]
    for r, (i, ln) in zip(body, data_lines):
        r.line, r.raw = i, ln
    res.rows = rows + body
    res.rows.sort(key=lambda r: r.line)
    res.format = "IPAC table"
    return res


def _cell(cells, colmap, key):
    j = colmap.get(key)
    return cells[j].strip() if j is not None and j < len(cells) else ""


def _parse_mapped(row, cells, colmap, units, ra_unit, default_equinox, coord_system, when):
    name = _cell(cells, colmap, "name")
    if not name and "name" not in colmap:  # unnamed name column: first non-coordinate text cell
        used = set(colmap.values())
        name = next((c for j, c in enumerate(cells) if j not in used and c and not _is_number(c)
                     and not _COORDLIKE.match(c)), "")
    row.name = " ".join(name.split()) or f"target {row.line}"
    row.url = _cell(cells, colmap, "url")
    row.notes = _cell(cells, colmap, "notes")
    eq = _cell(cells, colmap, "equinox")
    row.equinox = eq or default_equinox
    known = set(colmap.values())
    row.extra = {f"col{j + 1}": c for j, c in enumerate(cells) if j not in known and c}
    for key, attr in (("pm_ra", "pm_ra_cosdec"), ("pm_dec", "pm_dec")):
        v = _cell(cells, colmap, key)
        if v:
            try:
                setattr(row, attr, float(v))
            except ValueError:
                row.messages.append(f"ignored unreadable proper motion {v!r}")
    if row.pm_ra_cosdec or row.pm_dec:
        row.how.append("proper motion in mas/yr")

    ra_t, dec_t = _cell(cells, colmap, "ra"), _cell(cells, colmap, "dec")
    if not ra_t and not dec_t and "radec" in colmap:
        hit = _combined_cell(_cell(cells, colmap, "radec"))
        if hit:
            ra_t, dec_t = hit[2], hit[3]
    if not ra_t and "rah" in colmap:
        ra_t = " ".join(x for x in (_cell(cells, colmap, "rah"), _cell(cells, colmap, "ram"), _cell(cells, colmap, "ras")) if x)
    if not dec_t and "ded" in colmap:
        sign = _cell(cells, colmap, "design")
        d = _cell(cells, colmap, "ded")
        if sign == "-" and not d.startswith("-"):
            d = "-" + d
        dec_t = " ".join(x for x in (d, _cell(cells, colmap, "dem"), _cell(cells, colmap, "des")) if x)
    glon, glat = _cell(cells, colmap, "glon"), _cell(cells, colmap, "glat")
    if (not ra_t or not dec_t) and glon and glat and coord_system != "equatorial":
        _apply_galactic(row, glon, glat)
        return
    if not ra_t and not dec_t:
        if row.name and not row.name.startswith("target "):
            row.status = "resolve"
            row.messages.append("no coordinates — will look up the name")
        else:
            row.status, row.messages = "error", ["no coordinates and no name"]
        return
    if not ra_t or not dec_t:
        row.status, row.messages = "error", ["RA or Dec is missing"]
        return
    unit = units.get("ra") if ra_unit == "auto" else ra_unit
    _apply_radec(row, ra_t, dec_t, unit or "auto", when)


def _parse_delimited_noheader(row, cells, ra_unit, default_equinox, coord_system, when):
    """Fields without a header: find the RA/Dec pair; name = first text field."""
    for j in range(len(cells) - 1):
        try:
            parse_ra(cells[j])
            parse_dec(cells[j + 1])
        except CoordError:
            continue
        other = [c for k, c in enumerate(cells) if k not in (j, j + 1) and c]
        name = next((c for c in cells[:j] if c and not _is_number(c)), "") or \
            next((c for c in other if not _is_number(c) and not _URL.match(c) and not _EQUINOX_TOKEN.match(c)), "")
        row.name = name or f"target {row.line}"
        row.equinox = default_equinox
        after = cells[j + 2:]
        if after and _EQUINOX_TOKEN.match(after[0].strip()):
            row.equinox = after[0].strip()
        urls = [c for c in cells if _URL.match(c)]
        row.url = urls[0] if urls else ""
        known = {row.name, row.equinox, row.url, cells[j], cells[j + 1]}
        notes = [c for c in cells if c and c not in known]
        row.notes = " ".join(notes)
        if coord_system == "galactic":
            _apply_galactic(row, cells[j], cells[j + 1])
        else:
            _apply_radec(row, cells[j], cells[j + 1], ra_unit, when)
        return
    for j, c in enumerate(cells):
        hit = _combined_cell(c)
        if hit:
            names = [x for k, x in enumerate(cells) if k != j and x and not _is_number(x)]
            row.name = " ".join(names[0].split()) if names else f"target {row.line}"
            row.notes = " ".join(" ".join(x.split()) for x in names[1:])
            _apply_radec(row, hit[2], hit[3], ra_unit, when)
            return
    # no coordinate pair: a name?
    text = [c for c in cells if c]
    if len(text) >= 1 and not _is_number(text[0]):
        row.name, row.status = text[0], "resolve"
        row.messages.append("no coordinates — will look up the name")
    else:
        row.status, row.messages = "error", ["couldn't find an RA/Dec pair"]


def _finalize(rows: list[Row], ra_unit: str, header_unit: str | None = None, when=None) -> tuple[str, str]:
    """Decide what bare-decimal RAs mean for the whole list, then flag duplicates."""
    dec_rows = [r for r in rows if r.decimal_ra and r.status in ("ok", "warning")]
    decided, reason = "hours", "no bare-decimal RAs"
    if header_unit:
        decided, reason = header_unit, "from the column header"
    if dec_rows:
        vals = []
        for r in dec_rows:
            try:
                vals.append(float(r.ra_text))
            except ValueError:
                pass
        if ra_unit in ("hours", "deg"):
            decided, reason = ra_unit, "chosen by you"
        elif header_unit:
            decided, reason = header_unit, "from the column header"
        elif vals and max(vals) > 24:
            decided, reason = "deg", f"values up to {max(vals):.1f} > 24 can only be degrees"
        else:
            decided, reason = "hours", "AMBIGUOUS: every decimal RA ≤ 24 — assumed hours (JSkyCalc convention). Choose degrees if that's wrong."
        for r in dec_rows:
            r.how = [h for h in r.how if not h.startswith("RA:")]
            r.messages = [m for m in r.messages if "ambiguous" not in m]
            _reapply_ra(r, decided, when)
            if reason.startswith("AMBIGUOUS"):
                r.status = "warning"
                r.messages.append("decimal RA ≤ 24: read as hours — check the list-level setting")
    # duplicates
    seen: dict[str, Row] = {}
    for r in rows:
        if r.status in ("comment", "error"):
            continue
        key = r.name.strip().lower()
        if key in seen:
            r.status = "warning" if r.status == "ok" else r.status
            r.messages.append(f"duplicate name (also line {seen[key].line})")
        else:
            seen[key] = r
    return decided, reason


def _reapply_ra(r: Row, unit: str, when=None) -> None:
    v = float(r.ra_text)
    deg = v * 15.0 if unit == "hours" else v
    if not 0 <= deg < 360 + 1e-9:
        r.status = "error"
        r.messages.append(f"RA {v} out of range for {unit}")
        return
    pdec = parse_dec(r.dec_text)
    r.ra, r.dec = to_icrs(deg % 360, pdec.deg, r.equinox, when=when)
    r.how.insert(0, f"RA: decimal {'hours' if unit == 'hours' else 'degrees'}")


def rows_to_targets(rows: list[dict]) -> list[dict]:
    """Rows (as dicts from the UI, possibly edited) → target payloads (ok/warning only)."""
    out = []
    for r in rows:
        if r.get("status") not in ("ok", "warning") or r.get("ra") is None:
            continue
        if not (math.isfinite(r["ra"]) and math.isfinite(r["dec"])):
            continue
        out.append({"name": r["name"], "ra": r["ra"], "dec": r["dec"],
                    "pm_ra_cosdec": r.get("pm_ra_cosdec", 0.0), "pm_dec": r.get("pm_dec", 0.0),
                    "url": r.get("url", ""), "notes": r.get("notes", "")})
    return out


def write_jskycalc(targets: list[dict]) -> str:
    """Export in JSkyCalc's object-list format (name without blanks, hh mm ss dd mm ss 2000 [url])."""
    from ..core.timeutil import format_hms
    out = io.StringIO()
    out.write("# exported by artairmass — JSkyCalc object-list format (ICRS ≈ J2000)\n")
    for t in targets:
        name = re.sub(r"\s+", "_", t["name"].strip()) or "target"
        ra = format_hms(t["ra"] / 15.0, decimals=2).replace(":", " ")
        dec = format_hms(t["dec"], signed=True, decimals=1).replace(":", " ")
        out.write(f"{name:<20s} {ra}  {dec}  2000" + (f"  {t['url']}" if t.get("url") else "") + "\n")
    return out.getvalue()
