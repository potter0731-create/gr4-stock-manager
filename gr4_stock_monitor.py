#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GR IV HDF stock monitor for:
  1) Compuzone
  2) PLTHINK (유쾌한생각)

Default behavior:
- checks every 60 seconds
- alerts only when a site becomes clearly purchasable
- Windows toast + beep + opens the product page
- optional Telegram notification
- keeps previous status in stock_state.json to avoid duplicate alerts
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import traceback
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

try:
    from winotify import Notification, audio
except Exception:
    Notification = None
    audio = None

try:
    import winsound
except Exception:
    winsound = None


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
STATE_PATH = APP_DIR / "stock_state.json"
LOG_PATH = APP_DIR / "stock_monitor.log"

DEFAULT_CONFIG = {
    "check_interval_seconds": 60,
    "request_timeout_seconds": 15,
    "open_browser_on_stock": True,
    "windows_notification": True,
    "sound_alert": True,
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": ""
    }
}


@dataclass
class Product:
    key: str
    site: str
    title: str
    url: str
    fallback_url: Optional[str] = None


@dataclass
class CheckResult:
    status: str  # "in_stock", "out_of_stock", "unknown"
    reason: str
    price: Optional[str] = None
    fetched_url: Optional[str] = None


PRODUCTS = [
    Product(
        key="compuzone_gr4_hdf",
        site="컴퓨존",
        title="RICOH GR IV HDF (GR4 HDF)",
        url=(
            "https://www.compuzone.co.kr/product/product_detail.htm?"
            "ProductNo=1353375&BigDivNo=7&MediumDivNo=1133&DivNo=2636"
        ),
        fallback_url="https://m.compuzone.co.kr/product/product_detail.htm?ProductNo=1353375",
    ),
    Product(
        key="plthink_gr4_hdf",
        site="유쾌한생각(PLTHINK)",
        title="RICOH GR IV GR4 HDF",
        url=(
            "https://www.plthink.com/shop/shopdetail.html?"
            "branduid=1929762&search=gr4&sort=sellcnt&xcode=008&"
            "mcode=114&scode=001&GfDT=a2h3UFs%3D"
        ),
    ),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.5",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return DEFAULT_CONFIG.copy()

    try:
        user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"config.json 읽기 실패: {e}. 기본 설정을 사용합니다.")
        return DEFAULT_CONFIG.copy()

    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in user_config.items():
        if k == "telegram" and isinstance(v, dict):
            cfg["telegram"].update(v)
        else:
            cfg[k] = v
    return cfg


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def normalize_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def decode_response(r: requests.Response) -> str:
    # Korean shopping sites may use UTF-8 or EUC-KR/CP949.
    encoding = r.encoding
    if not encoding or encoding.lower() in {"iso-8859-1", "ascii"}:
        encoding = r.apparent_encoding or "utf-8"
    try:
        return r.content.decode(encoding, errors="replace")
    except LookupError:
        return r.content.decode("utf-8", errors="replace")


def fetch(session: requests.Session, url: str, timeout: int) -> tuple[str, str]:
    r = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return decode_response(r), r.url


def extract_price(text: str) -> Optional[str]:
    # Prefer Korean won-looking amounts large enough to be a camera price.
    matches = re.findall(r"(?<!\d)([1-9]\d{0,2}(?:,\d{3}){1,3})\s*원", text)
    values = []
    for m in matches:
        try:
            v = int(m.replace(",", ""))
            if 500_000 <= v <= 20_000_000:
                values.append((v, m))
        except ValueError:
            pass
    if not values:
        return None
    # Product price tends to be among the first plausible large amounts.
    return f"{values[0][1]}원"


def detect_compuzone(html: str, fetched_url: str) -> CheckResult:
    text = normalize_text(html)
    compact = re.sub(r"\s+", "", text)

    product_signals = ["GR IV HDF", "GR4 HDF", "1353375"]
    if not any(s.replace(" ", "") in compact for s in product_signals):
        return CheckResult("unknown", "상품 식별 문구를 찾지 못함", fetched_url=fetched_url)

    out_signals = [
        "입고일정이미정",
        "입고예정미정",
        "재입고알림신청",
        "품절",
        "일시품절",
        "판매중지",
    ]
    found_out = [s for s in out_signals if s in compact]
    if found_out:
        return CheckResult(
            "out_of_stock",
            "품절 신호: " + ", ".join(found_out),
            price=extract_price(text),
            fetched_url=fetched_url,
        )

    # Do not trust a generic '구매하기' alone. Require no sold-out marker plus
    # at least one ordering control phrase near a recognized product page.
    in_signals = ["바로구매", "장바구니", "구매하기", "주문하기"]
    found_in = [s for s in in_signals if s in compact]
    if found_in:
        return CheckResult(
            "in_stock",
            "품절 신호 없음 + 구매 가능 신호: " + ", ".join(found_in),
            price=extract_price(text),
            fetched_url=fetched_url,
        )

    return CheckResult(
        "unknown",
        "품절 신호는 없지만 구매 가능 신호도 확인되지 않음",
        price=extract_price(text),
        fetched_url=fetched_url,
    )


def detect_plthink(html: str, fetched_url: str) -> CheckResult:
    text = normalize_text(html)
    compact = re.sub(r"\s+", "", text)

    product_signals = ["1929762", "GR IV GR4 HDF", "GR4 HDF", "GR IV HDF"]
    if not any(s.replace(" ", "") in compact for s in product_signals):
        return CheckResult("unknown", "상품 식별 문구를 찾지 못함", fetched_url=fetched_url)

    # PLTHINK currently leaves a generic 구매하기 link in HTML even when sold out.
    # Therefore explicit sold-out markers always win.
    out_signals = ["품절", "일시품절", "SOLDOUT", "재입고알림"]
    upper_compact = compact.upper()
    found_out = [s for s in out_signals if s.upper() in upper_compact]
    if found_out:
        return CheckResult(
            "out_of_stock",
            "품절 신호: " + ", ".join(found_out),
            price=extract_price(text),
            fetched_url=fetched_url,
        )

    in_signals = ["구매하기", "장바구니", "바로구매", "BUYITNOW", "CART"]
    found_in = [s for s in in_signals if s.upper() in upper_compact]
    if found_in:
        return CheckResult(
            "in_stock",
            "품절 신호 없음 + 구매 가능 신호: " + ", ".join(found_in),
            price=extract_price(text),
            fetched_url=fetched_url,
        )

    return CheckResult(
        "unknown",
        "품절 신호는 없지만 구매 가능 신호도 확인되지 않음",
        price=extract_price(text),
        fetched_url=fetched_url,
    )


def check_product(session: requests.Session, product: Product, timeout: int) -> CheckResult:
    urls = [product.url] + ([product.fallback_url] if product.fallback_url else [])
    errors = []
    for url in urls:
        try:
            html, fetched_url = fetch(session, url, timeout)
            if product.key.startswith("compuzone"):
                result = detect_compuzone(html, fetched_url)
            else:
                result = detect_plthink(html, fetched_url)
            # If the first URL returns an unrecognizable/blocked page, try fallback.
            if result.status == "unknown" and product.fallback_url and url != product.fallback_url:
                errors.append(f"{url}: {result.reason}")
                continue
            return result
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    return CheckResult("unknown", " / ".join(errors) or "페이지 확인 실패")


def play_alert_sound() -> None:
    if winsound is None:
        return
    try:
        # Noticeable pattern, repeated twice.
        for _ in range(2):
            winsound.Beep(1400, 350)
            winsound.Beep(1800, 350)
            winsound.Beep(2200, 500)
            time.sleep(0.15)
    except Exception:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


def windows_toast(title: str, message: str, url: str) -> None:
    if Notification is None:
        log("윈도우 알림 모듈(winotify)을 사용할 수 없습니다.")
        return
    try:
        toast = Notification(
            app_id="GR4 HDF Stock Monitor",
            title=title,
            msg=message,
            duration="long",
        )
        if audio is not None:
            toast.set_audio(audio.Default, loop=False)
        toast.add_actions(label="상품 페이지 열기", launch=url)
        toast.show()
    except Exception as e:
        log(f"윈도우 알림 실패: {e}")


def telegram_notify(cfg: dict, message: str) -> None:
    tcfg = cfg.get("telegram", {})
    if not tcfg.get("enabled"):
        return
    token = str(tcfg.get("bot_token", "")).strip()
    chat_id = str(tcfg.get("chat_id", "")).strip()
    if not token or not chat_id:
        log("텔레그램이 enabled=true지만 bot_token/chat_id가 비어 있습니다.")
        return
    try:
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(
            endpoint,
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        log(f"텔레그램 알림 실패: {e}")


def alert(cfg: dict, product: Product, result: CheckResult) -> None:
    price = f" / {result.price}" if result.price else ""
    title = f"🔥 GR4 HDF 재고 발견 - {product.site}"
    message = f"{product.title}{price}\n지금 구매 가능 상태로 감지됨."
    log(f"ALERT: {title} | {result.reason}")

    if cfg.get("sound_alert", True):
        play_alert_sound()
    if cfg.get("windows_notification", True):
        windows_toast(title, message, product.url)
    telegram_notify(cfg, f"{title}\n{message}\n{product.url}")
    if cfg.get("open_browser_on_stock", True):
        try:
            webbrowser.open(product.url, new=2)
        except Exception as e:
            log(f"브라우저 열기 실패: {e}")


def run_once(cfg: dict, state: dict, session: requests.Session) -> bool:
    timeout = int(cfg.get("request_timeout_seconds", 15))
    changed = False

    for product in PRODUCTS:
        result = check_product(session, product, timeout)
        previous = state.get(product.key, {}).get("status")
        price_note = f", 가격={result.price}" if result.price else ""
        log(f"{product.site}: {result.status} ({result.reason}{price_note})")

        # Alert on transition into clearly in-stock. If no prior state exists and
        # it is already in stock, alert immediately as well.
        if result.status == "in_stock" and previous != "in_stock":
            alert(cfg, product, result)

        # Preserve previous known state on network/unknown failures, but record error.
        if result.status == "unknown" and previous in {"in_stock", "out_of_stock"}:
            stored_status = previous
        else:
            stored_status = result.status

        state[product.key] = {
            "site": product.site,
            "status": stored_status,
            "last_observed_status": result.status,
            "reason": result.reason,
            "price": result.price,
            "checked_at": now_text(),
            "url": product.url,
            "fetched_url": result.fetched_url,
        }
        changed = True

    if changed:
        save_state(state)
    return changed


def main() -> int:
    cfg = load_config()
    state = load_state()

    interval = max(20, int(cfg.get("check_interval_seconds", 60)))
    log("=" * 72)
    log("GR4 HDF 재고 감시 시작")
    log(f"감시 간격: 약 {interval}초 (사이트 부하 방지를 위해 ±5초 지터 적용)")
    log("종료: Ctrl+C 또는 창 닫기")

    session = requests.Session()

    while True:
        try:
            run_once(cfg, state, session)
        except KeyboardInterrupt:
            raise
        except Exception:
            log("예상하지 못한 오류:\n" + traceback.format_exc())

        sleep_for = max(20, interval + random.uniform(-5, 5))
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            break

    log("GR4 HDF 재고 감시 종료")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("사용자가 종료했습니다.")
        raise SystemExit(0)
