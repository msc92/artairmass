"""UI check for the Tools tab: every tool renders without errors."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from uicheck import seed, start_server  # noqa: E402


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    url = start_server()
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        seed(page, url, view="tools")
        page.click(".titem:has-text('Phoenix')")
        for key, label in [("slit", "Slit angle"), ("coords", "Coordinates"), ("finder", "Finder chart"), ("radio", "Radio"), ("space", "Space")]:
            page.click(f".toolbar .seg button:has-text('{label}')")
            page.wait_for_timeout(5000 if key == "finder" else 2500)
            page.screenshot(path=out / f"tool-{key}.png")
        b.close()
    print("\n".join(errors) if errors else "no console errors")


if __name__ == "__main__":
    main()
