"""UI check for list input: paste, ambiguity toggle, inline fix, name look-up, add, save, export."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from uicheck import start_server  # noqa: E402

MESSY = """# observing run 2026B — clusters
name, ra, dec, z
Abell 1795, 13:48:52.5, +26:35:34, 0.0625
Perseus    03 19 48.16  +41 30 42.1
3C 273   12:29:06.7 +02:03:08.6
Typo cl.   13:61:00  +26:00:00
NGC 1275
PKS 0745-191
"""


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    url = start_server()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(url)
        page.wait_for_selector(".topbar")
        page.click("button[title='Import / paste a list']")
        page.fill("textarea", MESSY)
        page.wait_for_selector("table.tbl tbody tr")
        page.wait_for_timeout(800)
        page.screenshot(path=out / "import-1-preview.png")
        # fix the typo row inline
        names = page.locator("table.tbl tbody tr td:nth-child(3) input")
        idx = [names.nth(i).input_value() for i in range(names.count())].index("Typo cl.")
        ra = page.locator("table.tbl tbody tr").nth(idx).locator("input").nth(1)
        ra.fill("13:51:00")
        ra.press("Tab")
        page.wait_for_timeout(600)
        # look up names (network permitting)
        btn = page.locator("button", has_text="Look up")
        if btn.count():
            btn.click()
            page.wait_for_timeout(6000)
        page.screenshot(path=out / "import-2-fixed.png")
        page.fill("input[placeholder='(unsaved)']", "2026B clusters")
        page.locator("button.primary", has_text="Add").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=out / "import-3-added.png")
        names = page.locator(".titem .nm").all_inner_texts()
        print("targets:", names)
        # ambiguous decimal list
        page.click("button[title='Import / paste a list']")
        page.fill("textarea", "a 13.81458 26.59278\nb 3.33 41.51\n")
        page.wait_for_selector(".banner.warn")
        page.screenshot(path=out / "import-4-ambiguous.png")
        page.keyboard.press("Escape")
        b.close()
    print("\n".join(errors) if errors else "no console errors")


if __name__ == "__main__":
    main()
