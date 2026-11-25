"""Compare the build's parts at other chain stores (順發 / PChome 24h / 欣亞).

For every config item with a "search" query, each store is searched once and the
cheapest listing that passes the item's rules is kept.

Per-item rules (all optional; fall back to the CoolPC rules):
  search         query string sent to the store, or {"*": default, "<store type>": override}
                 (欣亞 matches ANY word and returns only 20 hits, so give it one distinctive word)
  chain_match    like "match"; an entry may be a list of alternatives, e.g. ["*2", "x2", "2x"]
  chain_exclude  extra exclusions on top of "exclude"
Global rules in config["chains"]:
  exclude        exclusions for every item (pre-built PCs etc.)
  ratio          [lo, hi]: keep prices within lo..hi x today's CoolPC price (filters accessories / PCs)
"""
from __future__ import annotations

import json
import time
import urllib.parse

import requests

from .match import name_matches
from .products import SourceError, _get


# ---------------------------------------------------------------- store parsers (pure, testable)

def _num(s) -> int:
    digits = "".join(ch for ch in str(s) if ch.isdigit() or ch == ".")
    return int(round(float(digits))) if digits else 0


def parse_sunfar(html: str) -> list[dict]:
    i = html.find('"ptlist":[')
    if i < 0:
        raise SourceError("順發：找不到商品資料（ptlist）")
    arr, _ = json.JSONDecoder().raw_decode(html[i + len('"ptlist":'):])
    out, seen = [], set()
    for p in arr:
        ps = p.get("ps")
        if not ps or ps in seen:
            continue
        seen.add(ps)
        # "buy" is the page's internet_buy: N = 停產完售 / 缺貨暫停銷售 / 限門市購買
        buyable = p.get("buy") == "Y"
        out.append({"title": p.get("pname", ""), "price": _num(p.get("prod_price")), "in_stock": buyable,
                    "url": f"https://www.isunfar.com.tw/product/?prodseq={urllib.parse.quote(ps)}"})
    return out


def parse_pchome(data: dict) -> list[dict]:
    return [{"title": p.get("Name", ""), "price": _num(p.get("Price")),
             "url": f"https://24h.pchome.com.tw/prod/{urllib.parse.quote(p.get('Id', ''))}"}
            for p in data.get("Prods") or []]


def parse_sinya(html: str) -> list[dict]:
    marker = "const results = "
    i = html.find(marker)
    if i < 0:
        raise SourceError("欣亞：找不到商品資料（頁面結構可能改了）")
    try:
        arr, _ = json.JSONDecoder().raw_decode(html[i + len(marker):])
    except ValueError:
        raise SourceError("欣亞：商品資料格式無法解析")
    if not isinstance(arr, list):
        return []
    return [{"title": p.get("prod_title", ""), "price": _num(p.get("new_price")), "url": p.get("href", "")}
            for p in arr]


# ---------------------------------------------------------------- fetch

def search_store(store_type: str, query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    if store_type == "sunfar":
        return parse_sunfar(_get(f"https://www.isunfar.com.tw/search/1/{q}").text)
    if store_type == "pchome":
        return parse_pchome(_get(f"https://ecshweb.pchome.com.tw/search/v4.3/all/results?q={q}&page=1&pageCount=40",
                                 "application/json").json())
    if store_type == "sinya":
        return parse_sinya(_get(f"https://www.sinya.com.tw/search/0?keyword={q}").text)
    raise SourceError(f"未知的通路類型 {store_type}")


def pick(listings: list[dict], item: dict, chains_cfg: dict, coolpc_price: int | None) -> dict | None:
    rules = {"match": item.get("chain_match", item.get("match", [])),
             "exclude": item.get("exclude", []) + item.get("chain_exclude", []) + chains_cfg.get("exclude", [])}
    lo, hi = chains_cfg.get("ratio", [0.5, 2.0])
    ok = [l for l in listings
          if l["price"] > 0 and name_matches(l["title"], rules)
          and not (coolpc_price and not (lo * coolpc_price <= l["price"] <= hi * coolpc_price))]
    if not ok:
        return None
    # cheapest purchasable listing; if none can be bought, the cheapest one marked out of stock
    return min(ok, key=lambda l: (not l.get("in_stock", True), l["price"]))


def compare(cfg: dict, coolpc_items: dict, delay: float = 1.0, budget: float = 360.0) -> dict:
    """Return {"items": {slot: {store: offer|None}}, "errors": [{store, slot, error}]}.

    A store that fails twice in a row is skipped for the rest of the run, and the whole
    comparison stops after `budget` seconds, so a blocked store can't stall the daily job."""
    ch = cfg.get("chains") or {}
    out = {"items": {}, "errors": []}
    start = time.time()
    fails: dict[str, int] = {}
    for it in cfg["items"]:
        if not it.get("search"):
            continue
        slot = it["slot"]
        cp = (coolpc_items.get(slot) or {}).get("price")
        out["items"][slot] = {}
        for st in ch.get("stores", []):
            name = st["name"]
            q = it["search"]
            if isinstance(q, dict):          # {"*": default query, "<store type>": override}
                q = q.get(st["type"], q.get("*"))
            if not q:
                continue
            out["items"][slot][name] = None
            if fails.get(name, 0) >= 2:
                out["errors"].append({"store": name, "slot": slot, "error": "連續失敗，今天略過"})
                continue
            if time.time() - start > budget:
                out["errors"].append({"store": name, "slot": slot, "error": "比價時間用盡，略過"})
                continue
            t0 = time.time()
            try:
                out["items"][slot][name] = pick(search_store(st["type"], q), it, ch, cp)
                fails[name] = 0
                print(f"    [chains] {name:10s} {slot:10s} {time.time() - t0:5.1f}s ok", flush=True)
            except (SourceError, requests.RequestException, ValueError, KeyError) as e:
                fails[name] = fails.get(name, 0) + 1
                err = str(e) or type(e).__name__
                out["errors"].append({"store": name, "slot": slot, "error": err})
                print(f"    [chains] {name:10s} {slot:10s} {time.time() - t0:5.1f}s FAIL {err}", flush=True)
            time.sleep(delay)
    return out


def store_totals(cfg: dict, entry: dict) -> dict:
    """Per-store full-build total (only when the store has every counted part) and best-mix total."""
    ch = entry.get("chains") or {}
    stores = ["原價屋"] + [s["name"] for s in (cfg.get("chains") or {}).get("stores", [])]
    totals = {s: 0 for s in stores}
    mix, mix_ok = 0, True
    for it in cfg["items"]:
        if it.get("optional"):
            continue
        q = it.get("qty", 1)
        prices = {"原價屋": (entry["items"].get(it["slot"]) or {}).get("price")}
        for s, o in (ch.get("items", {}).get(it["slot"]) or {}).items():
            prices[s] = o["price"] if o and o.get("in_stock", True) else None
        for s in stores:
            if totals[s] is not None:
                totals[s] = totals[s] + prices[s] * q if prices.get(s) else None
        avail = [p for p in prices.values() if p]
        if avail:
            mix += min(avail) * q
        else:
            mix_ok = False
    return {"stores": totals, "mix": mix if mix_ok else None}
