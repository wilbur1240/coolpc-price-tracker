"""Track standalone products (e.g. a 3D printer) across several Taiwan shops.

Each product in config["products"] lists sources; every source yields offers
[{source, title, price, in_stock, url, ref}]. A failing source is recorded but
never aborts the run.

Source types:
  cyberbiz     Cyberbiz shop product page  (<url>.json, Shopify-like)
  woocommerce  WooCommerce product page    (variations JSON or JSON-LD)
  shopify      Shopify product page        (<url>.js)
  biggo        BigGo search, filtered to the listed major channels
  bambu_store  Bambu Lab official web store (USD, JSON-LD); reference only
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse

import requests

from .fetch import UA
from .match import name_matches, nz

TIMEOUT = 30
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6"}


class SourceError(RuntimeError):
    pass


def _get(url: str, accept: str = "text/html,*/*") -> requests.Response:
    import time
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers={**HEADERS, "Accept": accept}, timeout=(10, TIMEOUT))
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.ConnectionError as e:     # includes ConnectTimeout: host unreachable, don't wait it out
            raise SourceError(type(e).__name__)
        except requests.RequestException as e:
            last = type(e).__name__
        if attempt < 2:
            time.sleep(20 * (attempt + 1))
    raise SourceError(last)


# ---------------------------------------------------------------- filters

def title_ok(title: str, prod: dict) -> bool:
    """Listing/variant title passes the product's match/exclude rules."""
    return name_matches(title, prod)


def variant_ok(title: str, prod: dict) -> bool:
    """Shop variant title (e.g. 'P2S Combo / 單機') passes variant_exclude."""
    n = nz(title)
    return not any(nz(k) in n for k in prod.get("variant_exclude", []))


def listing_is_variant_excluded(title: str, prod: dict) -> bool:
    """A marketplace listing that is *only* an excluded variant, e.g. 'P2S Combo 3D列印機'.
    Combined listings like 'P2S / P2S Combo' (priced at the base model) are kept."""
    n = nz(title)
    for k in prod.get("variant_exclude", []):
        kk = nz(k)
        if kk in n:
            base = n.replace(kk, "")
            # keep if the base model also appears on its own ("p2s/p2scombo" -> "p2s/p2s")
            base_kw = [nz(x) for m in prod.get("match", []) for x in (m if isinstance(m, list) else [m])]
            if not any(base.count(b) >= 2 for b in base_kw) and "單機" not in n:
                return True
    return False


def in_price_range(price: int, prod: dict) -> bool:
    lo, hi = prod.get("price_min"), prod.get("price_max")
    return (lo is None or price >= lo) and (hi is None or price <= hi)


# ---------------------------------------------------------------- parsers (pure, testable)

def parse_cyberbiz(data: dict, prod: dict, source: str, url: str) -> list[dict]:
    out = []
    for v in data.get("variants", []):
        vt = v.get("title") or ""
        price = int(round(float(v.get("price") or 0)))
        if price <= 0 or not variant_ok(vt, prod):
            continue
        out.append({"source": source, "title": f"{data.get('title', '')}（{vt}）",
                    "price": price, "in_stock": bool(v.get("available")), "url": url})
    return out


def parse_shopify_js(data: dict, prod: dict, source: str, url: str) -> list[dict]:
    out = []
    for v in data.get("variants", []):
        vt = v.get("title") or ""
        price = int(round((v.get("price") or 0) / 100))   # cents
        if price <= 0 or not variant_ok(vt, prod):
            continue
        out.append({"source": source, "title": f"{data.get('title', '')}（{vt}）",
                    "price": price, "in_stock": bool(v.get("available")), "url": url})
    return out


def parse_woocommerce(html: str, prod: dict, source: str, url: str) -> list[dict]:
    """WooCommerce variable product: <form data-product_variations="[...]">; simple product: JSON-LD offer."""
    import html as H
    tm = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    title = H.unescape(tm.group(1)) if tm else ""
    m = re.search(r'data-product_variations="([^"]+)"', html)
    out = []
    if m:
        for v in json.loads(H.unescape(m.group(1))):
            vt = " / ".join(str(x) for x in (v.get("attributes") or {}).values())
            price = int(round(float(v.get("display_price") or 0)))
            if price <= 0 or not variant_ok(vt, prod):
                continue
            out.append({"source": source, "title": f"{title}（{vt}）", "price": price,
                        "in_stock": bool(v.get("is_in_stock")), "url": url})
        return out
    for blob in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(blob)
        except ValueError:
            continue
        for node in (j.get("@graph", [j]) if isinstance(j, dict) else j):
            if isinstance(node, dict) and node.get("@type") == "Product":
                offers = node.get("offers") or {}
                offers = offers[0] if isinstance(offers, list) else offers
                price = offers.get("price") or (offers.get("lowPrice") if offers.get("@type") == "AggregateOffer" else None)
                if price:
                    out.append({"source": source, "title": node.get("name", title), "price": int(round(float(price))),
                                "in_stock": "InStock" in (offers.get("availability") or ""), "url": url})
    return out


def biggo_items(html: str) -> list[dict]:
    """Extract the search result list embedded in BigGo's Next.js flight data."""
    i = html.find("ssrData")
    if i < 0:
        raise SourceError("BigGo: 找不到 ssrData（頁面結構可能改了）")
    marker = 'self.__next_f.push([1,"'
    s = html.rfind(marker, 0, i)
    e = html.find('"])</script>', i)
    if s < 0 or e < 0:
        raise SourceError("BigGo: 找不到資料區塊")
    dec = json.JSONDecoder()
    lit, _ = dec.raw_decode('"' + html[s + len(marker):e] + '"')
    j = lit.find('"ssrData":')
    sd, _ = dec.raw_decode(lit[j + len('"ssrData":'):])
    return sd.get("list") or []


def parse_biggo(items: list[dict], prod: dict, stores: list[str]) -> list[dict]:
    """Keep listings from whitelisted stores that look like the base product; cheapest per store."""
    best: dict[str, dict] = {}
    for it in items:
        if it.get("is_ad") or it.get("is_offline") or it.get("is_notfound") or it.get("is_expired"):
            continue
        store = ((it.get("store") or {}).get("name") or it.get("nindex") or "").strip()
        if not any(nz(s) in nz(store) for s in stores):
            continue
        title, price = it.get("title") or "", int(it.get("price") or 0)
        if (it.get("currency") or "TWD") != "TWD" or price <= 0:
            continue
        if not title_ok(title, prod) or listing_is_variant_excluded(title, prod) or not in_price_range(price, prod):
            continue
        offer = {"source": store, "title": title, "price": price, "in_stock": True,
                 "url": it.get("purl") or "", "via": "BigGo"}
        if store not in best or price < best[store]["price"]:
            best[store] = offer
    return sorted(best.values(), key=lambda o: o["price"])


def parse_bambu_store(html: str, region: str, variant: str) -> dict | None:
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m)
        except ValueError:
            continue
        for v in j.get("hasVariant", []) if isinstance(j, dict) else []:
            name = v.get("name", "")
            # "Bambu Lab P2S - P2S / China Taiwan"
            if region.lower() in name.lower() and f"- {variant} /".lower() in name.lower():
                o = v.get("offers") or {}
                return {"name": name, "price": float(o.get("price")), "currency": o.get("priceCurrency", "USD"),
                        "in_stock": "InStock" in (o.get("availability") or "")}
    return None


# ---------------------------------------------------------------- fetchers

def usd_twd() -> float | None:
    try:
        j = requests.get("https://open.er-api.com/v6/latest/USD", timeout=20).json()
        return float(j["rates"]["TWD"])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def fetch_source(src: dict, prod: dict) -> list[dict]:
    t, name = src["type"], src["name"]
    if t == "cyberbiz":
        url = src["url"].split("?")[0]
        data = _get(url + ".json", "application/json").json()
        offers = parse_cyberbiz(data, prod, name, url)
    elif t == "shopify":
        url = src["url"].split("?")[0]
        data = _get(url + ".js", "application/json").json()
        offers = parse_shopify_js(data, prod, name, url)
    elif t == "woocommerce":
        url = src["url"]
        offers = parse_woocommerce(_get(url).text, prod, name, url)
    elif t == "biggo":
        url = "https://biggo.com.tw/s/" + urllib.parse.quote(src["query"]) + "/"
        offers = parse_biggo(biggo_items(_get(url).text), prod, src.get("stores", []))
    elif t == "bambu_store":
        r = _get(src["url"])
        v = parse_bambu_store(r.text, src.get("region", "Taiwan"), src.get("variant", "P2S"))
        if not v:
            regions = sorted(set(re.findall(r'"name":\s*"Bambu Lab [^"/]+/\s*([^"]+)"', r.text)))[:8]
            raise SourceError(f"找不到 {src.get('region', 'Taiwan')} 的價格（實際網址 {r.url}，地區 {regions}）")
        rate = usd_twd() if v["currency"] == "USD" else 1.0
        twd = int(round(v["price"] * rate)) if rate else None
        cur = "US$" if v["currency"] == "USD" else v["currency"] + " "
        offers = [{"source": name, "title": f"{v['name']}（{cur}{v['price']:g}）", "price": twd,
                   "in_stock": v["in_stock"], "url": src["url"], "ref": True,
                   "note": f"{cur}{v['price']:g}，以匯率 {rate:.2f} 換算，未含運費／關稅" if rate else "匯率取得失敗"}]
    else:
        raise SourceError(f"未知的來源類型 {t}")
    for o in offers:
        o["group"] = name
        if src.get("reference_only"):
            o["ref"] = True
    return offers


def carry_forward(products: dict, hist: dict, date: str) -> None:
    """For sources that failed today, show their last successful offers, marked stale.
    Stale offers never count toward the best price or alerts."""
    for slot, p in products.items():
        failed = {e["source"] for e in p.get("errors", []) if not e.get("nomatch")}
        # hist[date] (if present) is still the earlier run of today, so it is searched first
        for d in sorted((d for d in hist if d <= date), reverse=True):
            if not failed:
                break
            prev = ((hist[d].get("products") or {}).get(slot) or {})
            got = {o.get("group") for o in prev.get("offers", []) if o.get("group") in failed and not o.get("stale")}
            for o in prev.get("offers", []):
                if o.get("group") in got and not o.get("stale"):
                    p["offers"].append({**o, "stale": d})
            failed -= got


ON_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
LOCAL_ONLY_MSG = "GitHub 主機在美國，這個來源擋海外連線；只在台灣 IP 執行時抓取"


def fetch_into(src: dict, prod: dict, offers: list, errors: list) -> None:
    try:
        got = fetch_source(src, prod)
        if not got:
            errors.append({"source": src["name"], "error": "沒有符合的商品（可能沒賣這個版本）", "nomatch": True})
        offers += got
    except (SourceError, requests.RequestException, ValueError, KeyError) as e:
        errors.append({"source": src["name"], "error": str(e) or type(e).__name__})


def finalize(offers: list, errors: list) -> dict:
    """One row per shop (fresh beats stale, then in-stock, then cheapest) and the best price.
    Stale and reference offers never become the best."""
    per: dict[str, dict] = {}
    rank = lambda o: (bool(o.get("stale")), not o["in_stock"], o.get("price") or 10**9)
    for o in offers:
        cur = per.get(o["source"])
        if cur is None or rank(o) < rank(cur):
            per[o["source"]] = o
    offers = list(per.values())
    counted = [o for o in offers if not o.get("ref") and not o.get("stale") and o.get("price")]
    in_stock = [o for o in counted if o["in_stock"]]
    pool = in_stock or counted
    best = min(pool, key=lambda o: o["price"]) if pool else None
    p = {"best": best, "offers": offers, "errors": errors}
    sort_offers(p)
    return p


def track_product(prod: dict) -> dict:
    """Return a history entry for one product."""
    offers, errors = [], []
    for src in prod["sources"]:
        if src.get("local_only") and ON_GITHUB:
            errors.append({"source": src["name"], "error": LOCAL_ONLY_MSG, "skipped": True})
            continue
        fetch_into(src, prod, offers, errors)
    return finalize(offers, errors)


def refresh_local_sources(prod: dict, p: dict) -> list[str]:
    """Re-fetch only this product's local_only sources and merge them into an existing
    day entry `p` (in place). Returns the names of the sources refreshed."""
    names = [s["name"] for s in prod["sources"] if s.get("local_only")]
    if not names:
        return []
    offers = [o for o in p.get("offers", []) if o.get("group") not in names]
    errors = [e for e in p.get("errors", []) if e["source"] not in names]
    for src in prod["sources"]:
        if src.get("local_only"):
            fetch_into(src, prod, offers, errors)
    p.update(finalize(offers, errors))
    return names


def sort_offers(p: dict) -> None:
    p["offers"].sort(key=lambda o: (bool(o.get("ref")), bool(o.get("stale")), o.get("price") or 10**9))


def track_all(cfg: dict) -> dict:
    return {p["slot"]: track_product(p) for p in cfg.get("products", [])}
