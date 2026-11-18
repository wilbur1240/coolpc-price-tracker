"""Match config target items against a price snapshot."""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r'\s+')


def nz(s: str) -> str:
    """Normalize for matching: NFKC (full-width -> half-width), lowercase, drop all whitespace."""
    return _WS.sub('', unicodedata.normalize('NFKC', s or '')).lower()


def in_category(row: dict, category: str | None) -> bool:
    return not category or nz(category) in nz(row['cat'])


def name_matches(name: str, item: dict) -> bool:
    n = nz(name)
    return (all(nz(k) in n for k in item.get('match', []))
            and not any(nz(k) in n for k in item.get('exclude', [])))


def candidates(rows: list[dict], item: dict) -> list[dict]:
    """All matching rows, cheapest first (stable: page order breaks ties)."""
    return sorted((r for r in rows if in_category(r, item.get('category')) and name_matches(r['name'], item)),
                  key=lambda r: r['price'])


def match_config(cfg: dict, rows: list[dict]) -> dict:
    """Return a history entry: {items, total, complete, missing, cat_min}."""
    items, total, missing = {}, 0, []
    for it in cfg['items']:
        c = candidates(rows, it)
        if c:
            best = c[0]
            q = it.get('qty', 1)
            items[it['slot']] = {"name": best['name'], "price": best['price'], "qty": q,
                                 "alts": len(c) - 1, "cat": best['cat']}
            if not it.get('optional'):
                total += best['price'] * q
        else:
            items[it['slot']] = None
            if not it.get('optional'):
                missing.append(it['slot'])
    cat_min = {}
    for w in cfg.get('watch_categories', []):
        ps = [r['price'] for r in rows if in_category(r, w)]
        if ps:
            cat_min[w] = {"min": min(ps), "count": len(ps)}
    return {"items": items, "total": total, "complete": not missing, "missing": missing, "cat_min": cat_min}
