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
    return f"{line}；{hits}/{n} 已達目標價"


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
            r = requests.post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                              json={"chat_id": tg_chat, "text": text, "disable_web_page_preview": True}, timeout=20)
            r.raise_for_status()
            sent.append("telegram")
        except requests.RequestException as e:
            print(f"[notify] telegram failed: {type(e).__name__}")  # don't echo URL (contains token)
    if not sent:
        print(f"[notify] (no channel configured / all failed) {title}\n{body}")
    return sent
