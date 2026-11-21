"""CLI: python -m tracker {run,render,notify-test}"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import notify, store
from .fetch import FetchError, decode, fetch
from .match import in_category, match_config
from .parse import category_counts, parse_html, parse_pipe_txt
from .products import carry_forward, sort_offers, track_all
from .render import render

MIN_ROWS = 1000
MIN_PER_CATEGORY = 3


class SanityError(RuntimeError):
    pass


def sanity_check(cfg: dict, rows: list[dict]):
    if len(rows) < MIN_ROWS:
        raise SanityError(f"只解析出 {len(rows)} 筆（門檻 {MIN_ROWS}），頁面結構可能改了或被擋")
    needed = set(cfg.get("watch_categories", [])) | {it.get("category") for it in cfg["items"] if it.get("category")}
    for c in sorted(needed):
        n = sum(1 for r in rows if in_category(r, c))
        if n < MIN_PER_CATEGORY:
            raise SanityError(f"分類「{c}」只有 {n} 筆，頁面結構可能改了")


def load_rows(args) -> list[dict]:
    if args.input:
        p = Path(args.input)
        if p.suffix == ".txt":
            return parse_pipe_txt(p.read_text(encoding="utf-8"))
        return parse_html(decode(p.read_bytes()))
    raw = fetch()
    if args.save_raw:
        Path(args.save_raw).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_raw).write_bytes(raw)
    return parse_html(decode(raw))


def cmd_run(args) -> int:
    cfg = store.load_config()
    date = args.date or store.today()
    try:
        rows = load_rows(args)
        sanity_check(cfg, rows)
    except (FetchError, SanityError, OSError) as e:
        print(f"[run] FAILED: {e}", file=sys.stderr)
        if not args.no_notify:
            notify.send("⚠️ 原價屋價格抓取失敗", f"{date}：{e}\n今天沒有寫入資料。", priority="high", tags="warning")
        return 1

    counts = category_counts(rows)
    print(f"[run] {date}: {len(rows)} 筆, {len(counts)} 類")
    for c, n in counts.items():
        print(f"    {n:5d}  {c}")

    hist = store.load_history()
    entry = match_config(cfg, rows)
    entry["count"] = len(rows)
    old = hist.get(date, {})
    if cfg.get("products") and not args.skip_products:
        entry["products"] = track_all(cfg)
        carry_forward(entry["products"], hist, date)
        for slot, p in entry["products"].items():
            sort_offers(p)
            b = p["best"]
            print(f"[products] {slot}: " + (f"最低 {b['price']:,}（{b['source']}）" if b else "沒有價格")
                  + f"，{len(p['offers'])} 個來源有價格" + (f"，失敗：{', '.join(e['source'] for e in p['errors'])}" if p["errors"] else ""))
    elif old.get("products"):
        entry["products"] = old["products"]
    hist[date] = entry

    alerts = notify.compute_alerts(cfg, hist, date)
    summary = notify.daily_summary(cfg, hist, date)
    print(f"[run] {summary}")
    for slot, t in entry["items"].items():
        print(f"    {slot:10s} {t['price'] if t else '缺項':>7}  {t['name'][:60] if t else ''}")

    if args.dry_run:
        print("[run] dry-run: 不寫檔、不通知")
        for a in alerts:
            print("    alert:", a)
        return 0

    send_daily = (cfg.get("notify") or {}).get("daily_summary", False)
    sent_alerts = old.get("alerts_sent")   # only alerts that actually reached a channel
    if not args.no_notify and (alerts or send_daily):
        if alerts and sent_alerts == alerts:
            print("[run] 今天已送過相同通知，略過")
        else:
            body = "\n".join(alerts + [summary]) if alerts else summary
            if notify.send(f"價格追蹤：{cfg.get('build_name', '目標配置')}", body,
                           priority="high" if alerts else "low", tags="moneybag"):
                sent_alerts = alerts
    entry["alerts"] = alerts
    if sent_alerts is not None:
        entry["alerts_sent"] = sent_alerts

    store.save_history(hist)
    store.save_snapshot(date, rows)
    out = render(cfg, hist, date, rows)
    print(f"[run] wrote {out.relative_to(store.ROOT)}")
    return 0


def cmd_render(args) -> int:
    cfg, hist = store.load_config(), store.load_history()
    date, rows = store.latest_snapshot()
    if rows is None:
        date, rows = (max(hist) if hist else store.today()), []
    print(f"[render] {render(cfg, hist, date, rows)}")
    return 0


def cmd_notify_test(args) -> int:
    if os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_CHAT_ID"):
        notify.telegram_diagnose()
    sent = notify.send("原價屋價格追蹤：測試通知", "如果你看到這則訊息，通知設定成功。", tags="white_check_mark")
    print(f"[notify-test] sent via: {sent or 'nothing'}")
    return 0 if sent else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="抓價格 → 比對 → 更新歷史 → 產生網頁 → 通知")
    r.add_argument("--input", help="改用本機檔案（evaluate.php 存下的 HTML，或 分類|價格|品名 的 .txt）")
    r.add_argument("--save-raw", help="把下載的原始 HTML 存到這個路徑（除錯用）")
    r.add_argument("--date", help="資料日期 YYYY-MM-DD（預設今天，台北時間）")
    r.add_argument("--no-notify", action="store_true", help="不發通知")
    r.add_argument("--skip-products", action="store_true", help="不抓 config.products（其他商品）的價格")
    r.add_argument("--dry-run", action="store_true", help="只印結果，不寫檔、不通知")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("render", help="用現有資料重新產生 docs/index.html").set_defaults(fn=cmd_render)
    sub.add_parser("notify-test", help="發一則測試通知").set_defaults(fn=cmd_notify_test)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
