"""Regenerate the README screenshots (docs/img/*). Deterministic: fixed site, list and time.

    python scripts/make_screenshots.py
"""
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from uicheck import seed, start_server  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "img"
TARGETS = [
    {"name": "Abell 1795", "ra": 207.21875, "dec": 26.59278},
    {"name": "Phoenix cluster", "ra": 356.1829, "dec": -42.72},
    {"name": "47 Tuc", "ra": 6.0236, "dec": -72.0813},
    {"name": "Hydra A", "ra": 139.5236, "dec": -12.0955},
    {"name": "Perseus", "ra": 49.9507, "dec": 41.5117},
    {"name": "RXJ1347-1145", "ra": 206.8775, "dec": -11.7528},
]
WHEN = "23:40"   # local time on the seeded night


def set_time(page, hhmm=WHEN, date="2026-10-07"):
    page.locator("input[type=date]").first.fill(date)
    page.wait_for_timeout(600)
    box = page.locator("input[title^='Local time']")
    box.click(); box.fill(hhmm); box.press("Enter")
    page.wait_for_timeout(1200)


def shot(page, name, full=False, clip=None):
    page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    png = page.screenshot(full_page=full, clip=clip)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.save(OUT / f"{name}.png", optimize=True)
    print("wrote", name, im.size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    url = start_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        seed(page, url, TARGETS, view="night")
        set_time(page)
        page.wait_for_selector(".js-plotly-plot"); page.wait_for_timeout(2500)
        page.mouse.move(820, 420); page.wait_for_timeout(600)
        shot(page, "night")
        page.click(".tab:has-text('Sky')"); page.wait_for_selector(".sky-svg"); page.wait_for_timeout(1800)
        shot(page, "sky")
        # animated sky across the night
        frames = []
        box = page.locator(".sky-svg").bounding_box()
        for k, hh in enumerate(["20:30", "21:30", "22:30", "23:30", "00:30", "01:30", "02:30", "03:30", "04:30", "05:30"]):
            set_time(page, hh, "2026-10-07" if hh > "12" else "2026-10-08")
            page.wait_for_timeout(500)
            png = page.screenshot(clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
            frames.append(Image.open(io.BytesIO(png)).convert("RGB").resize((560, 560), Image.LANCZOS).quantize(colors=128))
        frames[0].save(OUT / "sky-night.gif", save_all=True, append_images=frames[1:], duration=700, loop=0, optimize=True)
        print("wrote sky-night.gif")
        set_time(page)
        page.click(".tab:has-text('Season')"); page.wait_for_selector("h3:has-text('Observable hours')", timeout=30000)
        page.click(".toolbar .seg button:has-text('Whole list')"); page.wait_for_selector("h3:has-text('by month')", timeout=30000)
        page.wait_for_timeout(1500)
        shot(page, "season")
        page.click(".tab:has-text('Now')"); page.click(".titem:has-text('Phoenix')"); page.wait_for_timeout(2000)
        shot(page, "now")
        set_time(page)
        page.click("button[title='Import / paste a list']")
        page.fill("textarea", "# 2027A clusters — mixed formats are fine\nname, ra, dec, z\nAbell 2029, 15:10:56.1, +05:44:41, 0.077\nMACS J1149.5+2223   177.399d  22.399\nA2597   23 25 19.7  -12 07 27  J2000\nTypo cl.  13:61:00  +26:00:00\nPKS 0745-191\nZwCl 3146\n")
        page.wait_for_selector("table.tbl tbody tr"); page.wait_for_timeout(1200)
        shot(page, "import")
        page.keyboard.press("Escape")
        page.click(".tab:has-text('Tools')"); page.click(".toolbar .seg button:has-text('Finder chart')"); page.wait_for_timeout(6000)
        shot(page, "finder")
        page.click(".tab:has-text('Night')"); page.locator("body").click(position={"x": 2, "y": 890}); page.keyboard.press("r"); page.wait_for_timeout(2000)
        shot(page, "night-red")
        page.locator("body").click(position={"x": 2, "y": 890}); page.keyboard.press("t"); page.keyboard.press("t"); page.click(".tab:has-text('Now')"); page.wait_for_timeout(1500)
        shot(page, "now-light")
        page.close()
        ph = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        seed(ph, url, TARGETS, view="night")
        set_time(ph)
        ph.wait_for_selector(".js-plotly-plot"); ph.wait_for_timeout(2500)
        shot(ph, "phone-night")
        ph.locator(".tab:has-text('Sky')").click(); ph.wait_for_timeout(2000)
        shot(ph, "phone-sky")
        b.close()


if __name__ == "__main__":
    main()
