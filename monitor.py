#!/usr/bin/env python3
import html as html_lib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import requests
from bs4 import BeautifulSoup

STATE_PATH = Path(__file__).with_name("state.json")

SITES = {
    "compuzone": {
        "name": "컴퓨존",
        "urls": [
            "https://www.compuzone.co.kr/product/product_detail.htm?ProductNo=1353375&BigDivNo=7&MediumDivNo=1133&DivNo=2636",
            "https://m.compuzone.co.kr/product/product_detail.htm?ProductNo=1353375",
        ],
        "product_url": "https://www.compuzone.co.kr/product/product_detail.htm?ProductNo=1353375&BigDivNo=7&MediumDivNo=1133&DivNo=2636",
        "anchors": ["GR IV HDF", "GR4 HDF", "1353375"],
        "out_markers": [
            "입고 일정이 미정",
            "입고일정이 미정",
            "입고예정 미정",
            "재입고 알림 신청",
            "재입고알림신청",
            "일시품절",
            "품절",
            "판매중지",
            "재고없음",
        ],
        "in_markers": ["구매하기", "바로구매", "장바구니", "주문하기"],
    },
    "plthink": {
        "name": "유쾌한생각",
        "urls": [
            "https://www.plthink.com/shop/shopdetail.html?branduid=1929762&search=gr4&sort=sellcnt&xcode=008&mcode=114&scode=001&GfDT=a2h3UFs%3D",
        ],
        "product_url": "https://www.plthink.com/shop/shopdetail.html?branduid=1929762&search=gr4&sort=sellcnt&xcode=008&mcode=114&scode=001&GfDT=a2h3UFs%3D",
        "anchors": ["GR IV GR4 HDF", "GR IV HDF", "GR4 HDF", "1929762"],
        "out_markers": ["품절", "SOLD OUT", "Sold Out", "sold out", "재입고 알림"],
        "in_markers": ["구매하기", "바로구매", "장바구니", "주문하기"],
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def html_to_visible_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return _normalize_space(soup.get_text(" ", strip=True))


def product_region(text: str, anchors: Iterable[str], before: int = 800, after: int = 7000) -> str:
    """Limit marker checks to the product summary area to reduce footer/menu false positives."""
    lower = text.lower()
    positions = []
    for anchor in anchors:
        idx = lower.find(anchor.lower())
        if idx >= 0:
            positions.append(idx)
    if not positions:
        return text[:14000]
    idx = min(positions)
    return text[max(0, idx - before): idx + after]


def marker_hits(text: str, markers: Iterable[str]) -> list[str]:
    low = text.lower()
    return [m for m in markers if m.lower() in low]


def classify(site_key: str, raw_html: str) -> Tuple[str, Dict[str, object]]:
    cfg = SITES[site_key]
    text = html_to_visible_text(raw_html)
    region = product_region(text, cfg["anchors"])
    out_hits = marker_hits(region, cfg["out_markers"])
    in_hits = marker_hits(region, cfg["in_markers"])

    # Conservative rule: explicit sold-out signals always win, even if generic
    # '구매하기' markup/text remains on the page.
    if out_hits:
        status = "out_of_stock"
    elif in_hits:
        status = "in_stock"
    else:
        status = "unknown"

    details = {
        "out_hits": out_hits,
        "in_hits": in_hits,
        "region_preview": region[:800],
    }
    return status, details


def fetch_one(url: str, attempts: int = 2) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=HEADERS, timeout=(10, 25), allow_redirects=True)
            response.raise_for_status()
            if not response.content or len(response.content) < 500:
                raise RuntimeError(f"response too short: {len(response.content)} bytes")
            # Let requests/charset-normalizer choose a likely Korean encoding if needed.
            guessed = response.apparent_encoding
            if guessed:
                response.encoding = guessed
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2)
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def fetch_site(site_key: str) -> Tuple[str, Dict[str, object]]:
    cfg = SITES[site_key]
    errors = []
    for url in cfg["urls"]:
        try:
            raw_html = fetch_one(url)
            status, details = classify(site_key, raw_html)
            details["fetched_url"] = url
            details["bytes"] = len(raw_html.encode("utf-8", errors="ignore"))
            return status, details
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return "unknown", {"errors": errors}


def load_state() -> Dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_state(state: Dict[str, str]) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def telegram_send(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID GitHub Secrets가 필요합니다.")

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        endpoint,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=(10, 20),
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")


def test_telegram() -> int:
    telegram_send(
        "✅ GR4 HDF 재고 감시기 연결 테스트 성공\n"
        "GitHub Actions → Telegram 알림이 정상적으로 연결되었습니다."
    )
    print("Telegram test message sent.")
    return 0


def run_monitor() -> int:
    previous = load_state()
    current = dict(previous)
    notifications = []
    had_known_result = False

    for site_key, cfg in SITES.items():
        status, details = fetch_site(site_key)
        old = previous.get(site_key, "unknown")
        print(f"[{cfg['name']}] old={old} new={status}")
        print(json.dumps(details, ensure_ascii=False))

        if status == "unknown":
            # Never overwrite a known state with an uncertain network/parser result.
            continue

        had_known_result = True
        current[site_key] = status

        if status == "in_stock" and old != "in_stock":
            notifications.append(
                "🚨 GR4 HDF 재고 발견!\n"
                f"판매처: {cfg['name']}\n"
                "상태: 구매 가능 신호 확인\n"
                f"바로가기: {cfg['product_url']}"
            )

    if current != previous:
        save_state(current)
        print(f"State updated: {previous} -> {current}")
    else:
        print("State unchanged.")

    for message in notifications:
        telegram_send(message)
        print("Telegram restock notification sent.")

    # Unknown results are non-fatal so a temporary site block does not create noise.
    # If both sites are unknown, return success but make it conspicuous in logs.
    if not had_known_result:
        print("WARNING: both sites returned unknown; no state was changed.", file=sys.stderr)
    return 0


def main() -> int:
    if "--test-telegram" in sys.argv:
        return test_telegram()
    return run_monitor()


if __name__ == "__main__":
    raise SystemExit(main())
