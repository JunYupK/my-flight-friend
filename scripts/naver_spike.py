# ruff: noqa: ASYNC230, SIM115, BLE001, S112 — 일회성 spike 스크립트 (M2 계획 후 삭제)
"""Naver 항공권 spike — 페이지가 무엇을 그리고, 어떤 내부 API를 부르는지 기록한다.

사용 (OCI worker 컨테이너 — Playwright + Chromium 포함):
  python naver_spike.py --dep ICN --arr FUK --date 2026-11-12 --out /out/naver_fuk

산출물 (--out 디렉터리):
  page.html        최종 DOM
  page.png         전체 스크린샷
  requests.jsonl   naver 도메인 XHR/fetch 요청·응답 (본문은 앞부분만)
  bodies/NNN.json  JSON 응답 원문 (항공편 데이터 후보)
  summary.txt      셀렉터별 개수, 가격/시간 패턴 수, 큰 JSON 응답 목록
"""

import argparse
import asyncio
import json
import os
import re
import time

from playwright.async_api import async_playwright

V1_CARD = 'div[class*="combination_ConcurrentItemContainer"]'
PROBES = {
    "v1_card": V1_CARD,
    "v1_price": 'i[class*="item_num"]',
    "v1_airline": 'b[class*="airline_name"]',
    "v1_route_time": 'b[class*="route_time"]',
    "any_class_price": '[class*="price" i]',
    "any_class_airline": '[class*="airline" i]',
    "any_class_item": '[class*="item" i]',
    "li": "li",
}


def build_url(dep: str, arr: str, date: str) -> str:
    d = date.replace("-", "")
    dep_part = "SEL:city" if dep == "ICN" else f"{dep}:airport"
    arr_part = "SEL:city" if arr == "ICN" else f"{arr}:airport"
    return (
        "https://flight.naver.com/flights/international/"
        f"{dep_part}-{arr_part}-{d}?adult=1&isDirect=false&fareType=Y&tripType=OW"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dep", default="ICN")
    ap.add_argument("--arr", default="FUK")
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wait", type=int, default=45, help="결과 대기 최대 초")
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--chromium", default=None, help="Chromium 실행 파일 경로 (기본: Playwright 번들)")
    args = ap.parse_args()

    os.makedirs(os.path.join(args.out, "bodies"), exist_ok=True)
    url = build_url(args.dep, args.arr, args.date)
    log = open(os.path.join(args.out, "requests.jsonl"), "w", encoding="utf-8")
    big_json: list[tuple[int, int, str]] = []
    seq = 0

    async def on_response(resp):
        nonlocal seq
        req = resp.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        if "naver" not in req.url:
            return
        seq += 1
        n = seq
        entry = {
            "n": n,
            "t": round(time.monotonic() - t0, 2),
            "method": req.method,
            "url": req.url,
            "status": resp.status,
            "post": (req.post_data or "")[:4000],
            "ctype": resp.headers.get("content-type", ""),
        }
        try:
            body = await resp.body()
            entry["len"] = len(body)
            if "json" in entry["ctype"] or body[:1] in (b"{", b"["):
                path = os.path.join(args.out, "bodies", f"{n:03d}.json")
                with open(path, "wb") as f:
                    f.write(body)
                entry["body_head"] = body[:600].decode("utf-8", "replace")
                if len(body) > 20000:
                    big_json.append((n, len(body), req.url))
        except Exception as e:  # 리다이렉트 등 본문 없는 응답
            entry["body_err"] = str(e)[:200]
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.flush()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not args.headful, executable_path=args.chromium
        )
        ctx = await browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 2000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()
        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        t0 = time.monotonic()
        nav_err = ""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            nav_err = str(e)[:300]

        # 결과 로딩: 가격처럼 보이는 텍스트("123,400원")가 늘어나다 멈출 때까지 대기
        last, stable, t_first = -1, 0, None
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            try:
                text = await page.inner_text("body")
            except Exception:
                continue
            count = len(re.findall(r"\d{1,3}(?:,\d{3})+\s*원", text))
            if count and t_first is None:
                t_first = round(time.monotonic() - t0, 1)
            stable = stable + 1 if count == last and count > 0 else 0
            last = count
            if stable >= 3:
                break
            await page.mouse.wheel(0, 3000)

        html = await page.content()
        text = await page.inner_text("body")
        with open(os.path.join(args.out, "page.html"), "w", encoding="utf-8") as f:
            f.write(html)
        await page.screenshot(path=os.path.join(args.out, "page.png"), full_page=True)
        counts = {k: await page.locator(v).count() for k, v in PROBES.items()}
        # 가격 텍스트를 가진 가장 작은 반복 컨테이너의 class 후보
        classes = await page.evaluate(
            """() => {
                const out = {};
                for (const el of document.querySelectorAll('*')) {
                    const t = el.childElementCount === 0 ? el.textContent : '';
                    if (!/\\d{1,3}(,\\d{3})+\\s*원?$/.test((t || '').trim())) continue;
                    let c = el; for (let i = 0; i < 6 && c; i++) c = c.parentElement;
                    const key = (c && c.className && String(c.className).slice(0, 120)) || '?';
                    out[key] = (out[key] || 0) + 1;
                }
                return Object.entries(out).sort((a, b) => b[1] - a[1]).slice(0, 10);
            }"""
        )
        await browser.close()

    log.close()
    blocked = bool(re.search(r"captcha|비정상적인|자동화된|접근이 제한", text, re.IGNORECASE))
    lines = [
        f"url: {url}",
        f"nav_error: {nav_err or '-'}",
        f"final price-like texts: {last}  (first seen at {t_first}s)",
        f"block markers in text: {blocked}",
        f"xhr/fetch to naver: {seq}",
        "selector counts: " + json.dumps(counts, ensure_ascii=False),
        "price containers (6 levels up, top 10):",
        *[f"  {n:4d}  {c}" for c, n in classes],
        "big JSON responses (>20KB):",
        *[f"  #{n:03d} {size:>8d}B {u[:160]}" for n, size, u in big_json],
        "first 600 chars of body text:",
        text[:600].replace("\n", " | "),
    ]
    with open(os.path.join(args.out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
