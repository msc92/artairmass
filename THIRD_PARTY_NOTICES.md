# Third-party components

artairmass bundles the following so it works fully offline. Their licences apply to those files.

| Component | Where | Licence |
|---|---|---|
| [Plotly.js](https://github.com/plotly/plotly.js) 3.1.0 | `src/artairmass/web/vendor/plotly.min.js` | MIT |
| [Preact](https://github.com/preactjs/preact) + [htm](https://github.com/developit/htm) 3.1.1 (standalone build) | `src/artairmass/web/vendor/preact-htm.module.js` | MIT (Preact), Apache-2.0 (htm) |
| Yale Bright Star Catalogue, 5th rev. (Hoffleit & Warren 1991), via CDS (catalogue V/50) | `src/artairmass/data/bright_stars.json` (stars with V ≤ 5, reformatted) | public catalogue data; please cite Hoffleit & Warren (1991) |

**JSkyCalc** (John Thorstensen, Dartmouth College) is the program artairmass reimplements. No JSkyCalc
code is distributed here. Three published formulae it uses are reproduced in Python and credited in
the source: the Krisciunas & Schaefer (1991) moonlight model, the zenith-twilight polynomial, and the
Hardie (1962) airmass coefficients. `validation/fixtures/jskycalc_reference.json` contains numbers
JSkyCalc computed, used only as test references. To regenerate them you need your own copy of
`JSkyCalc.jar`.

Online services used at run time (optional): CDS Sesame (name resolution) and CDS hips2fits (finder-chart
images). Please acknowledge CDS when you publish results that use them.
