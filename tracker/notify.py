"""Alert rules + delivery via ntfy.sh and/or Telegram (configured through env vars).

Env vars (GitHub Secrets):
  NTFY_TOPIC            ntfy topic name (required for ntfy)
  NTFY_SERVER           default https://ntfy.sh
  NTFY_TOKEN            optional access token for protected topics
  TELEGRAM_BOT_TOKEN    Telegram bot token
  TELEGRAM_CHAT_ID      chat id to send to
  PAGE_URL              link included in messages
"""
from __future__ import annotations

import os

import requests

CHANGE_PCT = 5.0


def fmt(n) -> str:
    return f"{n:,}"


def compute_alerts(cfg: dict, hist: dict, date: str) -> list[str]:
    cur = hist[date]
    prev_dates = [d for d in hist if d < date]
    prev = hist[prev_dates[-1]] if prev_dates else None
    out = []
    for it in cfg["items"]:
        s, tp = it["slot"], it.get("target_price")
        t = cur["items"].get(s)
        if not t:
            continue
        p = (prev or {}).get("items", {}).get(s) if prev else None
        if tp is not None and t["price"] <= tp and (p is None or p["price"] > tp):
            out.append(f"🎯 {s} 達到目標價：{fmt(t['price'])} ≤ {fmt(tp)}（{t['name'][:40]}）")
        if p and p["price"]:
            pct = (t["price"] - p["price"]) / p["price"] * 100
            if abs(pct) >= CHANGE_PCT:
                arrow = "📉 降" if pct < 0 else "📈 漲"
                out.append(f"{arrow} {s} {pct:+.1f}%：{fmt(p['price'])} → {fmt(t['price'])}")
    if cur.get("complete"):
        past = [h["total"] for d, h in hist.items() if d < date and h.get("complete")]
        if past and cur["total"] < min(past):
            out.append(f"🏆 總價創新低：{fmt(cur['total'])}（先前最低 {fmt(min(past))}）")
    for s in cur.get("missing", []):
        if prev and prev.get("items", {}).get(s):
            out.append(f"⚠️ {s} 今天找不到符合品項（缺貨或改名？）")
    out += product_alerts(cfg, hist, date)
    return out


def _best(entry, slot):
    p = ((entry or {}).get("products") or {}).get(slot) or {}
    return p.get("best")


def product_alerts(cfg: dict, hist: dict, date: str) -> list[str]:
    out = []
    cur = hist[date]
    prev_dates = [d for d in hist if d < date]
    prev = hist[prev_dates[-1]] if prev_dates else None
    for prod in cfg.get("products", []):
        s, tp = prod["slot"], prod.get("target_price")
        b, pb = _best(cur, s), _best(prev, s)
        if not b:
            errs = (((cur.get("products") or {}).get(s) or {}).get("errors")) or []
            if errs:
                out.append(f"⚠️ {s} 今天所有價格來源都失敗：" + "；".join(f"{e['source']} {e['error']}" for e in errs))
            continue
        if tp is not None and b["price"] <= tp and (pb is None or pb["price"] > tp):
            out.append(f"🎯 {s} 達到目標價：{fmt(b['price'])} ≤ {fmt(tp)}（{b['source']}）")
        if pb and pb["price"]:
            pct = (b["price"] - pb["price"]) / pb["price"] * 100
            if abs(pct) >= CHANGE_PCT:
                arrow = "📉 降" if pct < 0 else "📈 漲"
                out.append(f"{arrow} {s} 最低價 {pct:+.1f}%：{fmt(pb['price'])} → {fmt(b['price'])}（{b['source']}）")
        past = [_best(h, s)["price"] for d, h in hist.items() if d < date and _best(h, s)]
        if past and b["price"] < min(past):
            out.append(f"🏆 {s} 創追蹤以來新低：{fmt(b['price'])}（{b['source']}）")
    return out


def daily_summary(cfg: dict, hist: dict, date: str) -> str:
    cur = hist[date]
    tgt = cfg.get("target_total")
    hits = sum(1 for it in cfg["items"] if it.get("target_price") is not None and cur["items"].get(it["slot"])
               and cur["items"][it["slot"]]["price"] <= it["target_price"])
    n = sum(1 for it in cfg["items"] if it.get("target_price") is not None)
    line = f"今日總價 {fmt(cur['total'])}" + ("（有缺項）" if not cur.get("complete") else "")
    if tgt:
        line += f"，目標 {fmt(tgt)}，差 {fmt(cur['total'] - tgt)}"
    line = f"{line}；{hits}/{n} 已達目標價"
    for prod in cfg.get("products", []):
        b = _best(cur, prod["slot"])
        tp = prod.get("target_price")
        if b:
            line += f"\n{prod['slot']} 最低 {fmt(b['price'])}（{b['source']}）" + (f"，目標 {fmt(tp)}" if tp else "")
        else:
            line += f"\n{prod['slot']} 今天沒有抓到價格"
    return line


def telegram_diagnose():
    """Print token shape (never the token), connectivity and getMe result."""
    import re
    import time
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    s = tok.strip()
    odd = sorted({repr(c) for c in s if not (c.isascii() and (c.isalnum() or c in ":-_"))})
    print(f"[diag] token: raw len={len(tok)}, stripped len={len(s)}, "
          f"format_ok={bool(re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{30,}', s))}, "
          f"starts_with_bot={s.lower().startswith('bot')}, odd_chars={odd}")
    print(f"[diag] chat id: len={len(chat.strip())}, digits_only={chat.strip().lstrip('-').isdigit()}")
    t = time.time()
    try:
        r = requests.get("https://api.telegram.org/", timeout=15)
        print(f"[diag] reach api.telegram.org: HTTP {r.status_code} in {time.time() - t:.1f}s")
    except requests.RequestException as e:
        print(f"[diag] reach api.telegram.org FAILED after {time.time() - t:.1f}s: {type(e).__name__}")
    t = time.time()
    try:
        r = requests.get("https://api.telegram.org/bot1234567890:" + "A" * 35 + "/getMe", timeout=15)
        print(f"[diag] fake-token getMe (expect 401): HTTP {r.status_code} in {time.time() - t:.1f}s")
    except requests.RequestException as e:
        print(f"[diag] fake-token getMe FAILED after {time.time() - t:.1f}s: {type(e).__name__}")
    if s:
        t = time.time()
        try:
            r = requests.get(f"https://api.telegram.org/bot{s}/getMe", timeout=15)
            j = r.json()
            info = j.get("result", {}).get("username") if j.get("ok") else j.get("description")
            print(f"[diag] getMe: HTTP {r.status_code} in {time.time() - t:.1f}s -> {info}")
        except (requests.RequestException, ValueError) as e:
            print(f"[diag] getMe FAILED after {time.time() - t:.1f}s: {type(e).__name__}")


def _post(url: str, **kw):
    """POST with a couple of retries on timeouts / connection errors."""
    for attempt in range(3):
        try:
            r = requests.post(url, timeout=30, **kw)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise


def send(title: str, body: str, priority: str = "default", tags: str = "") -> list[str]:
    """Send to every configured channel. Returns list of channels that succeeded."""
    url = os.environ.get("PAGE_URL", "").strip()
    sent = []
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        headers = {"Title": title.encode("utf-8"), "Priority": priority}
        if tags:
            headers["Tags"] = tags
        if url:
            headers["Click"] = url
        tok = os.environ.get("NTFY_TOKEN", "").strip()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        try:
            r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=20)
            r.raise_for_status()
            sent.append("ntfy")
        except requests.RequestException as e:
            print(f"[notify] ntfy failed: {e}")
    tg_tok, tg_chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tg_tok and tg_chat:
        text = f"{title}\n{body}" + (f"\n{url}" if url else "")
        try:
            _post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                  json={"chat_id": tg_chat, "text": text, "disable_web_page_preview": True})
            sent.append("telegram")
        except requests.HTTPError as e:
            desc = ""
            try:
                desc = e.response.json().get("description", "")
            except ValueError:
                pass
            print(f"[notify] telegram failed: HTTP {e.response.status_code} {desc}")  # never echo URL (has token)
        except requests.RequestException as e:
            print(f"[notify] telegram failed: {type(e).__name__}")
    if not sent:
        print(f"[notify] (no channel configured / all failed) {title}\n{body}")
    return sent
