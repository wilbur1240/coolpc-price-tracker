"""History (target items, kept forever) and full daily snapshots (gzip, last N days)."""
from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PRICES = DATA / "prices"
HISTORY = DATA / "history.json"
CONFIG = DATA / "config.json"
DOCS = ROOT / "docs"
KEEP_SNAPSHOT_DAYS = 45

TPE = dt.timezone(dt.timedelta(hours=8))


def today() -> str:
    return dt.datetime.now(TPE).date().isoformat()


def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def load_config() -> dict:
    return load_json(CONFIG)


def load_history() -> dict:
    return load_json(HISTORY, {}) or {}


def save_history(hist: dict):
    hist = dict(sorted(hist.items()))
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def save_snapshot(date: str, rows: list[dict], keep_days: int = KEEP_SNAPSHOT_DAYS) -> Path:
    PRICES.mkdir(parents=True, exist_ok=True)
    p = PRICES / f"{date}.json.gz"
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # mtime=0 -> identical content gives identical bytes (no noisy git diffs on re-runs)
    with open(p, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(data)
    cutoff = (dt.date.fromisoformat(date) - dt.timedelta(days=keep_days)).isoformat()
    for old in PRICES.glob("*.json.gz"):
        if old.name[:10] < cutoff:
            old.unlink()
    return p


def latest_snapshot() -> tuple[str, list[dict]] | tuple[None, None]:
    files = sorted(PRICES.glob("*.json.gz"))
    if not files:
        return None, None
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        return files[-1].name[:10], json.load(f)


def previous_entry(hist: dict, date: str):
    prev = [d for d in hist if d < date]
    return (prev[-1], hist[prev[-1]]) if prev else (None, None)
