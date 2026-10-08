"""Drive the real app in headless Chromium: click through features, capture console errors
and screenshots.  python scripts/uicheck.py <outdir> [scenario ...]
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

os.environ.setdefault("ARTAIRMASS_CONFIG_DIR", tempfile.mkdtemp(prefix="artairmass-cfg-"))
from artairmass.api.app import create_app  # noqa: E402


def start_server() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cfg = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return f"http://127.0.0.1:{port}/"


TARGETS = [
    {"name": "A1795", "ra": 207.21875, "dec": 26.59278},
    {"name": "Perseus", "ra": 49.9507, "dec": 41.5117},
    {"name": "Phoenix cl.", "ra": 356.1829, "dec": -42.72},
    {"name": "Hydra A", "ra": 139.5236, "dec": -12.0955},
    {"name": "47 Tuc", "ra": 6.0236, "dec": -72.0813},
]


def seed(page, url, targets=TARGETS, view="now", theme="dark", jd=None):
    page.goto(url)
    page.evaluate("""([t, v, th]) => {
        localStorage.setItem('artairmass.v1.targets', JSON.stringify(t.map((x, i) => ({...x, id: 'seed' + i, visible: true, slot: i < 8 ? i : null}))));
        localStorage.setItem('artairmass.v1.selectedId', JSON.stringify('seed0'));
        localStorage.setItem('artairmass.v1.view', JSON.stringify(v));
        localStorage.setItem('artairmass.theme', th);
    }""", [targets, view, theme])
    page.reload()
    page.wait_for_selector(".topbar", timeout=15000)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "uicheck-out")
    out.mkdir(parents=True, exist_ok=True)
    url = start_server()
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("console", lambda m: m.type in ("error", "warning") and errors.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        seed(page, url)
        page.wait_for_selector(".hero .big", timeout=15000)
        page.wait_for_timeout(1500)
        page.screenshot(path=out / "now-dark.png")

        page.keyboard.press("2")
        page.wait_for_selector(".js-plotly-plot", timeout=20000)
        page.wait_for_timeout(1500)
        page.screenshot(path=out / "night-dark.png", full_page=False)
        page.locator(".view").evaluate("el => el.scrollTo(0, 560)")
        page.wait_for_timeout(800)
        page.screenshot(path=out / "night-dark-tables.png")
        page.locator(".view").evaluate("el => el.scrollTo(0, 0)")
        page.click(".toolbar .seg button:has-text('Run')")
        page.wait_for_timeout(3500)
        page.screenshot(path=out / "night-run.png")
        page.click(".toolbar .seg button:has-text('Night')")
        page.wait_for_timeout(1500)
        page.keyboard.press("4")
        page.wait_for_selector(".sky-svg", timeout=15000)
        page.wait_for_timeout(1200)
        page.screenshot(path=out / "sky-dark.png")

        page.keyboard.press("5")
        page.wait_for_selector("table.tbl", timeout=15000)
        page.screenshot(path=out / "planets-dark.png")

        page.keyboard.press("2")
        page.keyboard.press("t")
        page.wait_for_timeout(1800)
        page.screenshot(path=out / "night-light.png")
        page.keyboard.press("1")
        page.wait_for_timeout(800)
        page.screenshot(path=out / "now-light.png")
        page.keyboard.press("r")
        page.wait_for_timeout(800)
        page.screenshot(path=out / "now-red.png")
        page.keyboard.press("4")
        page.wait_for_timeout(1200)
        page.screenshot(path=out / "sky-red.png")
        page.keyboard.press("2")
        page.wait_for_timeout(1800)
        page.screenshot(path=out / "night-red.png")

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.on("pageerror", lambda e: errors.append(f"[mobile pageerror] {e}"))
        seed(mobile, url)
        mobile.wait_for_selector(".hero .big", timeout=15000)
        mobile.wait_for_timeout(1000)
        mobile.screenshot(path=out / "now-mobile.png", full_page=True)
        browser.close()
    print("\n".join(errors) if errors else "no console errors")
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main()
