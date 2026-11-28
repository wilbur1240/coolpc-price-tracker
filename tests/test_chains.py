import json
import unittest
from pathlib import Path

from tracker import notify
from tracker.chains import parse_pchome, parse_sinya, parse_sunfar, pick, store_totals
from tracker.products import parse_woocommerce, track_product

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tests/fixtures/config_2026-11-18.json").read_text(encoding="utf-8"))
ITEMS = {it["slot"]: it for it in CFG["items"]}
CH = CFG["chains"]


def sunfar_page(rows):
    return '<script>var d={"filters":[],"ptlist":' + json.dumps(rows, ensure_ascii=False) + ',"x":1};</script>'


class ParserTest(unittest.TestCase):
    def test_sunfar_dedupe_and_stock(self):
        rows = [{"ps": "A1", "pname": "AMD R7-9700X", "prod_price": 11550.0, "buy": "Y"},
                {"ps": "A1", "pname": "AMD R7-9700X", "prod_price": 11550.0, "buy": "Y"},
                {"ps": "B2", "pname": "Kingston 64G(32G*2)", "prod_price": 18800.0, "buy": "N"}]
        out = parse_sunfar(sunfar_page(rows))
        self.assertEqual([(o["price"], o["in_stock"]) for o in out], [(11550, True), (18800, False)])
        self.assertTrue(out[0]["url"].endswith("prodseq=A1"))

    def test_pchome(self):
        out = parse_pchome({"Prods": [{"Id": "DRAH-1", "Name": "WD SN850X 2TB", "Price": 12988}]})
        self.assertEqual(out, [{"title": "WD SN850X 2TB", "price": 12988, "url": "https://24h.pchome.com.tw/prod/DRAH-1"}])

    def test_sinya(self):
        arr = [{"prod_id": "201530", "prod_title": "AMD【8核】Ryzen7 9700X", "new_price": "$11,550\\u5143",
                "href": "https:\\/\\/www.sinya.com.tw\\/prod\\/201530"}]
        page = "<script>const results = " + json.dumps(arr).replace("\\\\", "\\") + ";</script>"
        out = parse_sinya(page)
        self.assertEqual((out[0]["price"], out[0]["url"]), (11550, "https://www.sinya.com.tw/prod/201530"))
        self.assertEqual(parse_sinya("<script>const results = [];</script>"), [])


class PickTest(unittest.TestCase):
    def test_ram_alternative_spellings_and_prebuilt_excluded(self):
        listings = [
            {"title": "美光 Crucial PRO DDR5 5600 64GB(32G*2)", "price": 30399, "in_stock": False},
            {"title": "Micron 美光 PRO DDR5-6000 64G(32Gx2) 桌上型記憶體", "price": 31499},
            {"title": "(DIY)X870平台【威震江湖】(R7-9700X/64G(32G*2))", "price": 36600},
            {"title": "Kingston FURY 64G(32G*2) DDR4", "price": 15000},
        ]
        o = pick(listings, ITEMS["RAM 64GB"], CH, 29999)
        self.assertEqual(o["price"], 31499)          # in-stock preferred over cheaper out-of-stock

    def test_out_of_stock_fallback_and_ratio(self):
        gpu = ITEMS["GPU"]
        self.assertFalse(pick([{"title": "MSI RTX5060Ti 16G SHADOW", "price": 28990, "in_stock": False}],
                              gpu, CH, 25590)["in_stock"])
        # 1/4 of CoolPC price -> accessory / wrong item, dropped
        self.assertIsNone(pick([{"title": "RTX5060Ti 16G 支架", "price": 6000}], gpu, CH, 25590))


class TotalsAlertTest(unittest.TestCase):
    def entry(self, chain_gpu):
        items = {it["slot"]: {"price": 1000} for it in CFG["items"]}
        items["GPU"] = {"price": 25590}
        chains = {"items": {it["slot"]: {"順發": {"price": 900}, "PChome 24h": None, "欣亞": None}
                            for it in CFG["items"]}}
        chains["items"]["GPU"]["順發"] = chain_gpu
        return {"items": items, "total": 0, "complete": True, "chains": chains}

    def test_totals(self):
        e = self.entry({"price": 20000})
        t = store_totals(CFG, e)
        counted = [it for it in CFG["items"] if not it.get("optional")]
        self.assertEqual(t["stores"]["原價屋"], 25590 + 1000 * (len(counted) - 1))
        self.assertEqual(t["stores"]["順發"], 20000 + 900 * (len(counted) - 1))
        self.assertIsNone(t["stores"]["PChome 24h"])
        self.assertEqual(t["mix"], t["stores"]["順發"])

    def test_out_of_stock_not_counted(self):
        t = store_totals(CFG, self.entry({"price": 20000, "in_stock": False}))
        self.assertIsNone(t["stores"]["順發"])

    def test_chain_target_alert_once(self):
        hit = {"price": ITEMS["GPU"]["target_price"] - 100}
        hist = {"2026-11-24": self.entry({"price": 30000}), "2026-11-25": self.entry(hit)}
        a = notify.chain_alerts(CFG, hist, "2026-11-25")
        self.assertEqual(len([x for x in a if "GPU" in x and "順發" in x]), 1)
        hist["2026-11-26"] = self.entry(hit)
        self.assertFalse([x for x in notify.chain_alerts(CFG, hist, "2026-11-26") if "GPU" in x])


class LocalOnlyCarryForwardTest(unittest.TestCase):
    def test_skipped_store_gets_stale_offer_excluded_from_totals(self):
        from unittest import mock
        import tracker.chains as chains
        cfg = {"items": [{"slot": "CPU", "match": ["9700X"], "search": "9700X"}],
               "chains": {"stores": [{"name": "順發", "type": "sunfar", "local_only": True},
                                     {"name": "PChome 24h", "type": "pchome"}]}}
        with mock.patch.object(chains, "ON_GITHUB", True), \
             mock.patch.object(chains, "search_store", return_value=[{"title": "AMD 9700X", "price": 11550}]):
            out = chains.compare(cfg, {"CPU": {"price": 11550}}, delay=0)
        self.assertEqual(out["skipped"], ["順發"])
        self.assertIsNone(out["items"]["CPU"]["順發"])
        hist = {"2026-11-24": {"chains": {"items": {"CPU": {"順發": {"price": 11000, "title": "x"}}}}}}
        chains.carry_forward(out, hist, "2026-11-25")
        self.assertEqual(out["items"]["CPU"]["順發"]["stale"], "2026-11-24")
        e = {"items": {"CPU": {"price": 11550}}, "chains": out}
        t = chains.store_totals(cfg, e)
        self.assertIsNone(t["stores"]["順發"])            # stale never counts
        self.assertEqual(t["mix"], 11550)
        self.assertIsNone(notify._chain_best({"chains": {"items": {"CPU": {"順發": out["items"]["CPU"]["順發"]}}}}, "CPU"))


class Cc2Test(unittest.TestCase):
    CC2 = next(p for p in CFG["products"] if "Centauri" in p["slot"])

    def test_woocommerce_variants(self):
        import html
        vars_ = [{"attributes": {"attribute_規格": "新手列印包"}, "display_price": 18400, "is_in_stock": True},
                 {"attributes": {"attribute_規格": "CC2 Combo"}, "display_price": 15500, "is_in_stock": True},
                 {"attributes": {"attribute_規格": "CC2 單機"}, "display_price": 11900, "is_in_stock": False}]
        page = (f'<meta property="og:title" content="ELEGOO Centauri Carbon 2">'
                f'<form data-product_variations="{html.escape(json.dumps(vars_, ensure_ascii=False))}">')
        out = parse_woocommerce(page, self.CC2, "shop", "https://x")
        self.assertEqual([(o["price"], o["in_stock"]) for o in out], [(11900, False)])

    def test_nomatch_is_not_a_failure_alert(self):
        e = {"items": {}, "products": {self.CC2["slot"]: {"best": None, "offers": [], "errors": [
            {"source": "3D列印基地站", "error": "沒有符合的商品", "nomatch": True}]}}}
        self.assertEqual(notify.product_alerts(CFG, {"2026-11-25": e}, "2026-11-25"), [])


if __name__ == "__main__":
    unittest.main()
