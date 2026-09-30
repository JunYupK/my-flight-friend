"""Playwright 로 화면을 1200px / 390px 전체 스크린샷으로 저장하고 390px 가로 오버플로를 검사한다.

    python scripts/ui_snap.py --base http://localhost:8000 --out shots [--dark] [--chromium PATH] / /trips/1

파일명: <slug>-<width>[-dark].png. 390px 에서 가로 오버플로가 있으면 `OVERFLOW <path>` 출력 후 종료 코드 1.
"""

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
WIDTHS = (1200, 390)


def slug(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-") or "home"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--chromium", default=None, help="Chromium 실행 파일 경로 (기본: playwright 번들)")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    overflow = False
    theme = "dark" if args.dark else "light"

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, args=["--no-sandbox"])
        for width in WIDTHS:
            ctx = browser.new_context(viewport={"width": width, "height": 900}, user_agent=UA)
            # ThemeToggle 과 동일: localStorage.theme + <html class="dark">
            ctx.add_init_script(f"try {{ localStorage.setItem('theme', '{theme}'); }} catch (e) {{}}")
            page = ctx.new_page()
            for path in args.paths:
                page.goto(args.base.rstrip("/") + path, wait_until="networkidle")
                page.wait_for_timeout(500)
                name = f"{slug(path)}-{width}{'-dark' if args.dark else ''}.png"
                page.screenshot(path=str(out / name), full_page=True)
                if width == 390 and page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth"
                ):
                    print(f"OVERFLOW {path}")
                    overflow = True
            ctx.close()
        browser.close()
    return 1 if overflow else 0


if __name__ == "__main__":
    sys.exit(main())
