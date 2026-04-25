"""Capture README screenshots against a running Streamlit server.

Walks the user flow: login gate → demo mode → landing → sub-pages.

Usage:
    # terminal 1
    python -m streamlit run app/copilot.py --server.port 8530 --server.headless true

    # terminal 2
    python scripts/capture_screenshots.py --port 8530 --out docs/screenshots
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def capture(port: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"http://localhost:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,
        )
        page = ctx.new_page()

        # ── 00. Login gate ─────────────────────────────────────────────────
        print("-> 00_login")
        page.goto(base, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(2_500)
        page.screenshot(path=str(out_dir / "00_login.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 900})

        # Use the ?role=demo backdoor instead of clicking the button — clicks
        # don't always survive the timing dance with Streamlit's session state.
        page.goto(f"{base}/?role=demo", wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(13_000)  # calendar scan + briefing stream

        # ── 01. Landing — full page ────────────────────────────────────────
        print("-> 01_landing_full")
        page.screenshot(path=str(out_dir / "01_landing_full.png"), full_page=True)

        # ── 02. Hero + Risk Snapshot + briefing (above-the-fold) ───────────
        print("-> 02_hero_briefing")
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
        page.screenshot(path=str(out_dir / "02_hero_briefing.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 900})

        # ── 03. The Plan — before/after panel + flowing map ────────────────
        print("-> 03_the_plan")
        page.evaluate("""
          const el = [...document.querySelectorAll('.section-header-xl')][0];
          if (el) el.scrollIntoView({block: 'start'});
        """)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out_dir / "03_the_plan.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 900})

        # ── 04. Anomalies block ────────────────────────────────────────────
        print("-> 04_anomalies")
        page.evaluate("""
          const headers = [...document.querySelectorAll('.section-header')];
          const attn = headers.find(h => h.textContent.includes('Needs Attention'));
          if (attn) attn.scrollIntoView({block: 'start'});
        """)
        page.wait_for_timeout(800)
        page.screenshot(path=str(out_dir / "04_anomalies.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 900})

        # ── Sub-pages ───────────────────────────────────────────────────────
        # Navigate via sidebar link CLICKS, not page.goto(). page.goto loses
        # the Streamlit session (role state) and bounces to the login gate.
        def _nav(href_suffix: str) -> None:
            page.locator(
                f'[data-testid="stSidebarNavLink"][href$="/{href_suffix}"]'
            ).first.click()
            page.wait_for_load_state("networkidle", timeout=60_000)
            page.wait_for_timeout(5_000)

        for slug, href_suffix in [
            ("05_coordinator",  "Coordinator"),
            ("06_driver",       "Driver"),
            ("07_surplus",      "Surplus"),
            ("08_scorecard",    "Scorecard"),
            ("09_safety_audit", "Safety_Audit"),
        ]:
            print(f"-> {slug}")
            _nav(href_suffix)
            page.screenshot(path=str(out_dir / f"{slug}.png"), full_page=True)

        browser.close()

    files = sorted(out_dir.glob("*.png"))
    print(f"\nCaptured {len(files)} screenshots in {out_dir}:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8530)
    ap.add_argument("--out",  type=Path, default=Path("docs/screenshots"))
    args = ap.parse_args()
    try:
        capture(args.port, args.out)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
