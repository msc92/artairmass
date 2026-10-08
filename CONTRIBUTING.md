# Contributing to artairmass

Thanks for helping. artairmass is meant to be trusted at the telescope, so the bar is
**correct first, then pleasant to use**. Bug reports from real observing runs are especially
welcome.

## Ways to help

* **Report a number that looks wrong.** Use the *Accuracy discrepancy* issue template. Include the
  site, date/time, target coordinates, what artairmass shows, and the value you expected and where
  it came from (JSkyCalc, JPL Horizons, an observatory tool…).
* **Add or fix an observatory** in `src/artairmass/data/sites.json`. Give a source for the
  coordinates and use the IANA time zone (e.g. `America/Santiago`), never a fixed offset.
* **Teach the list parser a new format.** Paste a few anonymised lines into an issue, or open a PR
  that adds them as a test in `tests/test_parser.py`.
* **Improve the UI**: accessibility, mobile, new views. See *Front end* below.

## Development setup

```bash
git clone https://github.com/msc92/artairmass && cd artairmass
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium      # only for the UI checks
artairmass --no-browser --port 8765        # then open http://127.0.0.1:8765
```

The server serves files from `src/artairmass/web` directly, so front-end edits only need a
browser reload. Python edits need a server restart.

## Checks to run before a PR

```bash
pytest                                     # unit, API and JSkyCalc-comparison tests (~1 min)
pyflakes src tests scripts
python scripts/uicheck_full.py /tmp/ui     # drives every feature in headless Chromium
python scripts/uicheck_mobile.py /tmp/ui   # phone/tablet screenshots + overflow check
```

CI runs the same on Linux and macOS for Python 3.10–3.13.

## Ground rules

* **Accuracy.** Use astropy for astrometry rather than hand-rolled formulas. If you touch a
  calculation, add a test against an independent reference: astropy's full transform chain,
  astroplan, JPL Horizons, or the JSkyCalc fixtures. Document any known difference in
  `validation/VALIDATION.md`.
* **Offline first.** Nothing may need the network except name resolution and finder-chart
  images, and those must fail gracefully. Never add a CDN `<script>`. Vendor it and list it in
  `THIRD_PARTY_NOTICES.md`.
* **No build step.** The front end is plain ES modules + Preact/htm. Note for htm templates: a
  literal `<` in text starts a tag, so write `${"<"}`.
* **Never guess silently.** Ambiguous input (e.g. decimal RA ≤ 24) must be flagged to the user.
* **Charts.** Colour follows the target (its slot), never its rank. Keep one y-scale (the
  altitude labels on the airmass plot are the same axis, relabelled). In red night-vision mode,
  tell series apart by dash pattern and label, never by hue.
* Keep PRs focused; describe *why* as well as what. Screenshots help for UI changes.

## Project layout

```
src/artairmass/core   astronomy: time, sites, sky model, almanac, tracks, tables, best-time, tools
src/artairmass/io     list parser, coordinate parsing, Sesame resolver
src/artairmass/api    FastAPI app (stateless JSON API + static UI)
src/artairmass/plots  matplotlib exports
src/artairmass/web    the UI (Preact + htm + Plotly, vendored)
validation/           JSkyCalc oracle harness, fixtures, VALIDATION.md
scripts/              UI checks and README screenshot generator
```

By contributing you agree your work is released under the BSD-3-Clause licence of this repository.
Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).
