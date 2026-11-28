import json
import unittest
from pathlib import Path

from tracker import notify
from tracker.products import (biggo_items, listing_is_variant_excluded, parse_bambu_store, parse_biggo,
                              parse_cyberbiz)

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tests/fixtures/config_2026-11-18.json").read_text(encoding="utf-8"))
P2S = next(p for p in CFG["products"] if p["slot"] == "Bambu Lab P2S")
STORES = next(s for s in P2S["sources"] if s["type"] == "biggo")["stores"]


def biggo_html(items):
    """Build a page shaped like BigGo's Next.js flight payload."""
    payload = '16:["$","$L2b",null,{"initValue":{"ssrData":' + json.dumps({"total": len(items), "list": items},
                                                                          ensure_ascii=False) + "}}]\n"
    lit = json.dumps(payload, ensure_ascii=False)[1:-1]
    return f'<html><script>self.__next_f.push([1,"{lit}"])</script></html>'


def item(store, title, price, **kw):
    return {"nindex": "x", "title": title, "price": price, "currency": "TWD", "purl": "https://example.com/" + store,
            "store": {"name": store}, **kw}


class CyberbizTest(unittest.TestCase):
    def test_variants_exclude_combo(self):
        data = json.loads((ROOT / "tests/fixtures/cyberbiz_kiden.json").read_text(encoding="utf-8"))
        offers = parse_cyberbiz(data, P2S, "Kiden", "https://x")
        self.assertEqual(sorted(o["price"] for o in offers), [23500, 24500, 27500])
        self.assertTrue(all("Combo" not in o["title"].split("（")[1] for o in offers))
        self.assertFalse(next(o for o in offers if o["price"] == 23500)["in_stock"])


class BigGoTest(unittest.TestCase):
    ITEMS = [
        item("酷澎 Coupang", "Bambu Lab 拓竹 P2S / P2S Combo 3D 列印機 - 高速靜穩專業級 單機", 24500),
        item("酷澎 Coupang", "Bambu Lab P2S Combo 3D 列印機 多色列印", 34000),
        item("酷澎 Coupang", "拓竹 Bambu Lab H2 P2S X2 副廠硬化鋼噴嘴 0.4mm", 150),
        item("萬家福線上購物", "[拓竹Bambu Lab ]P2S 3D列印機", 23500),
        item("萬家福線上購物", "[拓竹 Bambu Lab] P2S Combo3D列印機", 32500),
        item("momo購物網", "【Bambu Lab】【領券再折】P2S/P2S Combo 3D列印機 廠商配送", 23500),
        item("蝦皮商城", "Bambu Lab P2S 3D列印機 廠商配送", 24500),
        item("蝦皮購物", "Bambu Lab 拓竹 P2S 3D列印機", 19000),            # individual seller: not whitelisted
        item("博客來網路書店", "Bambu Lab P2S and AMS 2 Pro User Guide", 1374),
        item("momo購物網", "Bambu Lab P2S 3D列印機", 21000, is_ad=True),  # ad: skipped
    ]

    def test_extract_and_filter(self):
        items = biggo_items(biggo_html(self.ITEMS))
        self.assertEqual(len(items), len(self.ITEMS))
        offers = parse_biggo(items, P2S, STORES)
        self.assertEqual({o["source"]: o["price"] for o in offers},
                         {"酷澎 Coupang": 24500, "萬家福線上購物": 23500, "momo購物網": 23500, "蝦皮商城": 24500})

    def test_combo_only_listing(self):
        self.assertTrue(listing_is_variant_excluded("Bambu Lab P2S Combo 3D 列印機", P2S))
        self.assertFalse(listing_is_variant_excluded("P2S/P2S Combo 3D列印機", P2S))
        self.assertFalse(listing_is_variant_excluded("P2S / P2S Combo 單機", P2S))
        self.assertFalse(listing_is_variant_excluded("Bambu Lab P2S 3D列印機", P2S))


class BambuStoreTest(unittest.TestCase):
    def test_jsonld_variant(self):
        ld = {"@type": "ProductGroup", "hasVariant": [
            {"name": "Bambu Lab P2S - P2S Combo / China Taiwan", "offers": {"price": "719", "priceCurrency": "USD"}},
            {"name": "Bambu Lab P2S - P2S / China Taiwan",
             "offers": {"price": "519", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}},
            {"name": "Bambu Lab P2S - P2S / Singapore", "offers": {"price": "699", "priceCurrency": "SGD"}}]}
        html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        v = parse_bambu_store(html, "Taiwan", "P2S")
        self.assertEqual((v["price"], v["currency"], v["in_stock"]), (519.0, "USD", True))


class CarryForwardTest(unittest.TestCase):
    def test_failed_source_reuses_last_success(self):
        from tracker.products import carry_forward
        hist = {
            "2026-11-19": {"products": {"P": {"offers": [{"source": "momo", "price": 1, "group": "BigGo"}]}}},
            "2026-11-20": {"products": {"P": {"offers": [{"source": "momo", "price": 2, "group": "BigGo"},
                                                         {"source": "A", "price": 3, "group": "A"}]}}},
        }
        today = {"P": {"best": {"price": 3}, "offers": [{"source": "A", "price": 3, "group": "A"}],
                       "errors": [{"source": "BigGo", "error": "HTTP 429"}]}}
        carry_forward(today, hist, "2026-11-21")
        stale = [o for o in today["P"]["offers"] if o.get("stale")]
        self.assertEqual([(o["source"], o["price"], o["stale"]) for o in stale], [("momo", 2, "2026-11-20")])
        self.assertEqual(today["P"]["best"], {"price": 3})


class ProductAlertTest(unittest.TestCase):
    def entry(self, price, source="momo"):
        return {"items": {}, "total": 0, "complete": True,
                "products": {"Bambu Lab P2S": {"best": {"price": price, "source": source}, "offers": [], "errors": []}}}

    def test_target_and_new_low(self):
        hist = {"2026-11-20": self.entry(23500), "2026-11-21": self.entry(19900)}
        a = notify.product_alerts(CFG, hist, "2026-11-21")
        self.assertTrue(any("達到目標價" in x for x in a))
        self.assertTrue(any("新低" in x for x in a))
        self.assertTrue(any("📉" in x for x in a))   # -15%

    def test_no_alert_when_unchanged(self):
        hist = {"2026-11-20": self.entry(23500), "2026-11-21": self.entry(23500)}
        self.assertEqual(notify.product_alerts(CFG, hist, "2026-11-21"), [])

    def test_all_sources_failed(self):
        e = {"items": {}, "products": {"Bambu Lab P2S": {"best": None, "offers": [],
                                                         "errors": [{"source": "A", "error": "HTTP 403"}]}}}
        a = notify.product_alerts(CFG, {"2026-11-21": e}, "2026-11-21")
        self.assertEqual(len(a), 1)
        self.assertIn("都失敗", a[0])


if __name__ == "__main__":
    unittest.main()
