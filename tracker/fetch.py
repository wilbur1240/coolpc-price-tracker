"""Download CoolPC evaluate.php (Big5 / cp950)."""
from __future__ import annotations

import time

import requests

URL = "https://www.coolpc.com.tw/evaluate.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


class FetchError(RuntimeError):
    pass


def decode(raw: bytes) -> str:
    for enc in ('cp950', 'big5hkscs'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('cp950', 'replace')


def fetch(url: str = URL, retries: int = 3, timeout: float = 45) -> bytes:
    """Return raw bytes of the page. Raises FetchError after all retries fail."""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
    }
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                raise FetchError(f"HTTP {r.status_code}")
            if len(r.content) < 50_000:
                raise FetchError(f"response too small ({len(r.content)} bytes)")
            return r.content
        except (requests.RequestException, FetchError) as e:
            last = e
            if attempt < retries:
                time.sleep(10 * attempt)
    raise FetchError(f"fetch {url} failed after {retries} attempts: {last}")
