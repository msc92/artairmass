"""Full click-through of every feature in the real app (headless Chromium).

Prints a checklist; exits non-zero if any step fails or the page logs an error.
    python scripts/uicheck_full.py <outdir>
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from uicheck import TARGETS, seed, start_server  # noqa: E402

results = []


def step(name):
    def deco(fn):
        def run(page, out):
            try:
                fn(page, out)
                results.append((name, True, ""))
            except Exception as e:  # noqa: BLE001
                results.append((name, False, f"{type(e).__name__}: {e}".splitlines()[0][:200]))
                slug = re.sub(r"\W+", "_", name)
                page.screenshot(path=out / f"FAIL-{slug}.png")
        run.name = name
        return run
    return deco


@step("site picker: search and switch to Paranal, then back")
def s_site(page, out):
    page.click(".picker > .btn:has-text('Las Campanas')")
    page.fill(".popover input", "paranal")
    page.keyboard.press("Enter")
    page.wait_for_selector(".picker > .btn:has-text('Paranal')")
    page.click(".picker > .btn:has-text('Paranal')")
    page.fill(".popover input", "magellan")
    page.keyboard.press("Enter")
    page.wait_for_selector(".picker > .btn:has-text('Las Campanas')")


@step("custom site: add, appears in picker, delete")
def s_usersite(page, out):
    page.click(".picker > .btn:has-text('Las Campanas')")
    page.click(".popover .row:has-text('Add a custom site')")
    page.fill("label:has-text('Name') input", "Cerro Calán")
    page.fill("label:has-text('Latitude') input", "-33.3964")
    page.fill("label:has-text('Longitude') input", "-70.5367")
    page.fill("label:has-text('Elevation') input", "860")
    page.fill("label:has-text('Time zone') input", "America/Santiago")
    page.click(".dialog button:has-text('Save site')")
    page.wait_for_selector(".picker > .btn:has-text('Cerro Calán')")
    page.click(".picker > .btn:has-text('Cerro Calán')")
    page.click(".popover .row:has-text('Edit')")
    page.click(".dialog button:has-text('Delete site')")
    page.wait_for_selector(".picker > .btn:has-text('Las Campanas')", timeout=10000)


@step("time: type local time, step forward/back, sidereal step, live")
def s_time(page, out):
    box = page.locator("input[title^='Local time']")
    box.click()
    box.fill("23:30")
    box.press("Enter")
    page.wait_for_timeout(600)
    assert page.locator(".clock b").nth(0).inner_text().startswith("23:30"), page.locator(".clock b").nth(0).inner_text()
    page.locator("body").click(position={"x": 5, "y": 880})
    page.keyboard.press("f")
    page.wait_for_timeout(600)
    assert page.locator(".clock b").nth(0).inner_text().startswith("00:30")
    page.keyboard.press("b")
    page.wait_for_timeout(600)
    lst0 = page.locator(".clock b").nth(2).inner_text()
    step_in = page.locator("input[title^='Timestep']")
    step_in.fill("1 t")
    step_in.press("Enter")
    page.locator("body").click(position={"x": 5, "y": 880})
    page.wait_for_timeout(500)
    page.keyboard.press("f")
    page.wait_for_timeout(1500)
    lst1 = page.locator(".clock b").nth(2).inner_text()
    assert lst0[:5] == lst1[:5], (lst0, lst1)  # one sidereal day keeps LST
    step_in.fill("1 h")
    step_in.press("Enter")
    page.locator("body").click(position={"x": 5, "y": 880})
    page.keyboard.press("]")
    page.wait_for_timeout(600)
    page.keyboard.press("n")
    page.wait_for_selector(".btn.live")


@step("add target by coordinates and by planet name")
def s_add(page, out):
    page.click("button[title='Add one target']")
    page.fill("input[placeholder^='Name']", "M87")
    page.fill("input[placeholder^='RA']", "12h30m49.4s")
    page.fill("input[placeholder^='Dec']", "+12d23m28s")
    page.click("form button:has-text('Add')")
    page.wait_for_selector(".titem:has-text('M87')")
    page.click("button[title='Add one target']")
    page.fill("input[placeholder^='Name']", "Jupiter")
    page.click("form button:has-text('Add')")
    page.wait_for_selector(".titem:has-text('Jupiter')")


@step("name resolution (network): add 'Abell 2029' by name")
def s_resolve(page, out):
    page.click("button[title='Add one target']")
    page.fill("input[placeholder^='Name']", "Abell 2029")
    page.click("form button:has-text('Add')")
    page.wait_for_selector(".titem:has-text('Abell 2029')", timeout=20000)


@step("Now view: hero airmass, coordinate editor applies")
def s_now(page, out):
    page.keyboard.press("1")
    page.click(".titem:has-text('M87')")
    page.wait_for_selector(".target-title h1:has-text('M87')")
    page.fill(".coord-edit label:has-text('Dec') input", "+12:24:00")
    page.click(".coord-edit button:has-text('Apply')")
    page.wait_for_timeout(1200)
    assert "+12:24:00" in page.locator(".kv dd").first.inner_text()
    page.screenshot(path=out / "full-now.png")


@step("filter, j/k navigation, hide and remove a target")
def s_list_ops(page, out):
    page.keyboard.press("/")
    page.keyboard.type("perse")
    assert page.locator(".titem").count() == 1
    page.keyboard.press("Escape")
    page.locator("body").click(position={"x": 5, "y": 880})
    page.keyboard.press("j")
    page.keyboard.press("k")
    page.locator(".titem:has-text('Jupiter') input.vis").click()
    assert not page.locator(".titem:has-text('Jupiter') input.vis").is_checked()
    page.locator(".titem:has-text('Jupiter')").hover()
    page.locator(".titem:has-text('Jupiter') .rm").click()
    assert page.locator(".titem:has-text('Jupiter')").count() == 0


@step("import dialog: paste, look up, add; save list; reload list")
def s_import(page, out):
    page.click("button[title='Import / paste a list']")
    page.fill("textarea", "name,ra,dec\nRXJ1347,13:47:30.6,-11:45:10\nZwCl 3146\n")
    page.wait_for_selector("table.tbl tbody tr")
    lk = page.locator("button:has-text('Look up')")
    if lk.count():
        lk.click()
        page.wait_for_timeout(6000)
    page.locator(".dialog button.primary:has-text('Add')").click()
    page.wait_for_selector(".titem:has-text('RXJ1347')")
    page.once("dialog", lambda d: d.accept("run 2027A"))
    page.click(".side-head .picker > .btn")
    page.click(".popover .row:has-text('Save as')")
    page.wait_for_selector(".side-head .picker > .btn:has-text('run 2027A')")
    page.click(".side-head .picker > .btn")
    page.click(".popover .row:has-text('Sort by RA')")
    page.click(".side-head .picker > .btn")
    with page.expect_download() as dl:
        page.click(".popover .row:has-text('Export JSkyCalc list')")
    assert dl.value.suggested_filename.endswith(".txt")


@step("Night view: plot, altitude axis, limit, click sets time, exports, hourly CSV, run mode")
def s_night(page, out):
    page.keyboard.press("2")
    page.wait_for_selector(".js-plotly-plot")
    page.click(".toolbar .seg button:has-text('Altitude')")
    page.wait_for_timeout(800)
    page.click(".toolbar .seg button:has-text('Airmass')")
    lim = page.locator("label:has-text('limit X') input")
    lim.fill("1.8")
    lim.press("Enter")
    page.wait_for_timeout(1500)
    assert "limit X = 1.8" in page.locator(".js-plotly-plot").first.inner_text()
    t0 = page.locator(".clock b").nth(0).inner_text()
    box = page.locator(".js-plotly-plot .nsewdrag").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    page.wait_for_timeout(800)
    assert page.locator(".clock b").nth(0).inner_text() != t0
    for fmt in ("PNG", "PDF", "SVG", "CSV"):
        page.click("button:has-text('Export')")
        with page.expect_download() as dl:
            page.click(f".popover .row:has-text('{fmt}')")
        assert dl.value.suggested_filename.lower().endswith(fmt.lower())
    with page.expect_download() as dl:
        page.click("h3:has-text('Hourly') button:has-text('CSV')")
    page.click(".toolbar .seg button:has-text('Run')")
    page.wait_for_selector("h3:has-text('Observing run')", timeout=20000)
    page.screenshot(path=out / "full-run.png")
    page.click(".toolbar .seg button:has-text('Night')")


@step("Season view: selected + list, Moon presets, JSkyCalc table")
def s_season(page, out):
    page.keyboard.press("3")
    page.wait_for_selector("h3:has-text('Observable hours per night')", timeout=30000)
    page.click(".toolbar .seg button:has-text('Dark')")
    page.wait_for_timeout(2500)
    page.click(".toolbar .seg button:has-text('Whole list')")
    page.wait_for_selector("h3:has-text('by month')", timeout=30000)
    page.wait_for_selector("h3:has-text('Seasonal observability')")
    page.click(".toolbar .seg button:has-text('Any moon')")
    page.screenshot(path=out / "full-season.png")


@step("Sky view: click selects, z/o/r keys, h adds bright star, c adds cursor target")
def s_sky(page, out):
    page.keyboard.press("4")
    page.wait_for_selector(".sky-svg")
    page.wait_for_timeout(1000)
    svg = page.locator(".sky-svg")
    b = svg.bounding_box()
    n0 = page.locator(".titem").count()
    svg.click(position={"x": b["width"] * 0.5, "y": b["height"] * 0.5})
    page.mouse.move(b["x"] + b["width"] * 0.55, b["y"] + b["height"] * 0.45)
    for k in ("z", "o", "r"):
        page.keyboard.press(k)
    page.keyboard.press("h")
    page.wait_for_timeout(500)
    page.keyboard.press("c")
    page.wait_for_timeout(1500)
    assert page.locator(".titem").count() >= n0 + 2, (n0, page.locator(".titem").count())


@step("Planets: table renders, row click makes a planet the target")
def s_planets(page, out):
    page.keyboard.press("5")
    page.wait_for_selector("table.tbl tbody tr")
    page.click("table.tbl tbody tr:has-text('Saturn')")
    page.wait_for_selector(".titem:has-text('Saturn')")


@step("Tools: slit, coordinates (galactic → add), finder, radio, space")
def s_tools(page, out):
    page.click(".titem:has-text('RXJ1347')")
    page.keyboard.press("6")
    page.click(".toolbar .seg button:has-text('Slit angle')")
    page.wait_for_timeout(1500)
    page.click(".toolbar .seg button:has-text('Coordinates')")
    page.wait_for_selector("h3:has-text('Result')")
    page.once("dialog", lambda d: d.accept("GC"))
    page.click("button:has-text('Add as target')")
    page.wait_for_selector(".titem:has-text('GC')")
    page.click(".toolbar .seg button:has-text('Finder chart')")
    page.wait_for_timeout(5000)
    page.click(".toolbar .seg button:has-text('Radio')")
    page.wait_for_selector("th:has-text('LST start')")
    page.click(".toolbar .seg button:has-text('Space')")
    page.wait_for_selector("th:has-text('Days in window')")


@step("Settings dialog: change airmass model and text size, persist")
def s_settings(page, out):
    page.click("button[title='Settings']")
    page.select_option(".dialog label:has-text('Airmass formula') select", "young")
    page.fill(".dialog label:has-text('Text size') input", "1.1")
    page.click(".dialog button:has-text('Save')")
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector(".topbar")
    page.click("button[title='Settings']")
    assert page.locator(".dialog label:has-text('Airmass formula') select").input_value() == "young"
    page.select_option(".dialog label:has-text('Airmass formula') select", "hardie")
    page.fill(".dialog label:has-text('Text size') input", "1")
    page.click(".dialog button:has-text('Save')")


@step("Help dialog and themes (t cycles, r toggles red)")
def s_help(page, out):
    page.locator("body").click(position={"x": 5, "y": 880})
    page.keyboard.press("?")
    page.wait_for_selector(".dialog h2:has-text('artairmass')")
    page.keyboard.press("Escape")
    for _ in range(3):
        page.keyboard.press("t")
    page.keyboard.press("r")
    assert page.evaluate("document.documentElement.dataset.theme") == "red"
    page.keyboard.press("r")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "uicheck-full")
    out.mkdir(parents=True, exist_ok=True)
    url = start_server()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errors.append(m.text))
        seed(page, url, TARGETS[:4])
        page.wait_for_selector(".hero")
        for fn in (s_site, s_usersite, s_time, s_add, s_resolve, s_now, s_list_ops, s_import, s_night,
                   s_season, s_sky, s_planets, s_tools, s_settings, s_help):
            fn(page, out)
        b.close()
    for name, ok, msg in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {msg}" if msg else ""))
    print("console errors:", errors or "none")
    sys.exit(0 if all(ok for _, ok, _ in results) and not errors else 1)


if __name__ == "__main__":
    main()
