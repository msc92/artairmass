"""Screenshot every view at phone and tablet widths; report horizontal overflow and errors."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from uicheck import seed, start_server  # noqa: E402

VIEWS = ["now", "night", "season", "sky", "planets", "tools"]


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    url = start_server()
    problems = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, vp in (("phone", {"width": 390, "height": 844}), ("tablet", {"width": 820, "height": 1180})):
            page = b.new_page(viewport=vp, device_scale_factor=2, has_touch=True, is_mobile=name == "phone")
            page.on("pageerror", lambda e: problems.append(f"{name}: pageerror {e}"))
            seed(page, url)
            page.wait_for_selector(".topbar")
            for v in VIEWS:
                page.evaluate(f"localStorage.setItem('artairmass.v1.view', JSON.stringify('{v}'))")
                page.reload()
                page.wait_for_selector(".topbar")
                page.wait_for_timeout(3500 if v in ("night", "season") else 1800)
                over = page.evaluate("() => document.documentElement.scrollWidth") - vp["width"]
                if over > 1:
                    problems.append(f"{name}/{v}: page scrolls horizontally by {over}px")
                page.screenshot(path=out / f"{name}-{v}.png", full_page=True)
            page.close()
        b.close()
    print("\n".join(problems) if problems else "no overflow, no errors")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
