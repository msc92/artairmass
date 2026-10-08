"""Command-line entry point: ``artairmass`` launches the local web app."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from . import __version__


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free port")


def _open_ui(url: str, app_window: bool) -> None:
    if app_window:  # chromeless window if a Chromium-family browser is installed
        candidates = ["google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium",
                      "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
        for c in candidates:
            exe = shutil.which(c) or (c if c.startswith("/") and os.path.exists(c) else None)
            if exe:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1440,920"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        print("No Chromium-family browser found for --app; opening a normal tab.")
    webbrowser.open(url)


def serve(host: str, port: int, open_browser: bool, app_window: bool) -> None:
    import uvicorn

    from .api.app import create_app

    port = _free_port(port)
    url = f"http://{host}:{port}/"
    print(f"artairmass {__version__} → {url}   (Ctrl-C to quit)", flush=True)
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1.0), _open_ui(url, app_window)), daemon=True).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def selftest() -> int:
    """Quick offline sanity check of the install."""
    from datetime import date

    from . import astro_setup
    from .core.night import plan_night
    from .core.sites import get_site
    from .core.targets import Target

    st = astro_setup.iers_status()
    print(f"IERS predictions from {st.predictive_start} (table to {st.table_end}); "
          f"{'STALE — run `artairmass update-data` when online' if st.stale else 'fresh'}; ephemeris {st.ephemeris}")
    from astropy.time import Time

    from .core.timeutil import hm_local

    site = get_site("lco")
    t0 = time.time()
    n, _ = plan_night(site, date.today(), [Target("A1795", 207.2187, 26.5928)])
    eve, morn = n.twilight["astronomical"]
    fmt = lambda jd: hm_local(Time(jd, format="jd"), site.tz) if jd else "—"  # noqa: E731
    print(f"Las Campanas tonight: astronomical dark {fmt(eve)}–{fmt(morn)} local "
          f"({time.time() - t0:.2f} s to compute)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="artairmass", description="Offline-first observation planner.")
    p.add_argument("--version", action="version", version=f"artairmass {__version__}")
    sub = p.add_subparsers(dest="cmd")
    sv = sub.add_parser("serve", help="run the web app (default)")
    for q in (p, sv):
        q.add_argument("--host", default="127.0.0.1")
        q.add_argument("--port", type=int, default=8765)
        q.add_argument("--no-browser", action="store_true", help="don't open a browser")
        q.add_argument("--app", action="store_true", help="open in a chromeless app window")
    sub.add_parser("update-data", help="download fresh IERS-A / leap-second tables (needs network)")
    sub.add_parser("selftest", help="quick offline check of the installation")
    a = p.parse_args(argv)

    if a.cmd == "update-data":
        from . import astro_setup
        try:
            print(astro_setup.update_data())
        except Exception as err:
            print(f"update failed (offline?): {err}", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "selftest":
        return selftest()
    serve(a.host, a.port, not a.no_browser, a.app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
