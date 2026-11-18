"""Render docs/index.html (single self-contained static page)."""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from .store import DOCS, TPE

TEMPLATE = Path(__file__).with_name("template.html")


def render(cfg: dict, hist: dict, date: str, rows: list[dict], out: Path | None = None) -> Path:
    out = out or DOCS / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cfg": cfg,
        "history": hist,
        "date": date,
        "rows": [{"cat": r["cat"], "group": r.get("group", ""), "name": r["name"], "price": r["price"]} for r in rows],
        "generated": dt.datetime.now(TPE).strftime("%Y-%m-%d %H:%M"),
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(f"{cfg.get('build_name', '目標配置')} 價格追蹤")
    page = TEMPLATE.read_text(encoding="utf-8").replace("__TITLE__", title).replace("__DATA__", blob)
    out.write_text(page, encoding="utf-8")
    (out.parent / ".nojekyll").touch()
    return out
