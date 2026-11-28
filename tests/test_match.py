import json
import unittest
from pathlib import Path

from tracker.match import match_config, nz
from tracker.parse import parse_html, parse_option, parse_pipe_txt

ROOT = Path(__file__).resolve().parent.parent

# The sample file uses short category labels; map them to the real page names
# so the test exercises the same category rules (CASE / 電源供應器 traps) as production.
REAL_CAT = {
    "CPU": "處理器 CPU",
    "主機板": "主機板 MB",
    "記憶體": "記憶體 RAM",
    "SSD": "固態硬碟 M.2｜SSD",
    "散熱器": "散熱器｜散熱墊｜散熱膏",
    "顯示卡": "顯示卡VGA",
    "機殼": "CASE 機殼(+電源)",
    "電源": "電源供應器",
}


def load_sample():
    rows = parse_pipe_txt((ROOT / "data/sample_2026-11-18.txt").read_text(encoding="utf-8"))
    for r in rows:
        r["cat"] = REAL_CAT[r["cat"]]
    return rows


class SampleMatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "tests/fixtures/config_2026-11-18.json").read_text(encoding="utf-8"))
        cls.res = match_config(cls.cfg, load_sample())

    def price(self, slot):
        return self.res["items"][slot]["price"]

    def test_item_prices(self):
        expect = {"CPU": 11550, "GPU": 25590, "主機板": 8390, "RAM 64GB": 29999, "SSD 2TB": 12111,
                  "PSU 850W": 2390, "散熱器": 1490, "機殼": 3690, "GPU 升級": 45990}
        for slot, p in expect.items():
            with self.subTest(slot=slot):
                self.assertEqual(self.price(slot), p)

    def test_total_excludes_optional(self):
        self.assertEqual(self.res["total"], 95210)
        self.assertTrue(self.res["complete"])

    def test_excludes(self):
        self.assertNotIn("EVO", self.res["items"]["散熱器"]["name"])
        self.assertNotIn("X3D", self.res["items"]["CPU"]["name"])

    def test_missing_marks_incomplete(self):
        cfg = dict(self.cfg, items=self.cfg["items"] + [{"slot": "X", "category": "CPU", "match": ["不存在的型號"]}])
        res = match_config(cfg, load_sample())
        self.assertIsNone(res["items"]["X"])
        self.assertFalse(res["complete"])
        self.assertEqual(res["missing"], ["X"])

    def test_normalize(self):
        self.assertEqual(nz("Phantom　Spirit 120"), "phantomspirit120")
        self.assertIn(nz("5060Ti"), nz("DUAL-RTX5060TI-O16G"))


class ParseTest(unittest.TestCase):
    def test_option_text(self):
        self.assertEqual(parse_option("｛Intel Core Ultra 5 245K｝【14核】4.2G, $6650 ★"),
                         ("｛Intel Core Ultra 5 245K｝【14核】4.2G", 6650))
        self.assertEqual(parse_option("某商品▼下殺到 11/30 23:59, $6990↘$5990 ◆ ★")[1], 5990)
        self.assertEqual(parse_option("XX, $1,299")[1], 1299)
        self.assertIsNone(parse_option("↪ 買主機板送好禮 價值 $500"))
        self.assertIsNone(parse_option("共有商品 170 樣，熱賣 32"))

    def test_html_unclosed_tags(self):
        page = """<table><tbody id=tbdy>
<TR bgColor=efefe0><TD class=w>4<TD class=t>處理器 CPU<TD noWrap>
<SELECT name=n4 class=s>
<OPTION value=0 selected class=bf>共有商品 50 樣
<OPTGROUP LABEL='AMD AM5'>
<OPTION disabled value=2>&#x21AA; 送好禮價值 $8,500</OPTION>
<OPTION value=3>AMD R7 9700X 代理盒裝, $11550 ★</OPTION>
<OPTION value=4>AMD R5 9600X, $8990↘$8150 ◆
</OPTGROUP></SELECT><SELECT name=q4><OPTION value=1>1<OPTION value=2>2</SELECT>
<TH align=right id=p4><TD class=d></TR>
<TR><TD class=w>5<TD class=t>主機板 MB <TD noWrap><SELECT name=n5>
<OPTION value=2>微星 MAG B850 TOMAHAWK, $8390</OPTION></SELECT></TR></table>"""
        rows = parse_html(page)
        self.assertEqual([(r["cat"], r["group"], r["price"]) for r in rows],
                         [("處理器 CPU", "AMD AM5", 11550), ("處理器 CPU", "AMD AM5", 8150), ("主機板 MB", "", 8390)])


if __name__ == "__main__":
    unittest.main()
