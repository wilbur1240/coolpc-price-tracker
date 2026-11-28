"""The 2026-11-28 final purchase list (原價屋 quote 71,709)."""
import json
import unittest
from pathlib import Path

from tracker import notify
from tracker.match import match_config

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "data/config.json").read_text(encoding="utf-8"))

R = lambda cat, price, name: {"cat": cat, "group": "", "name": name, "price": price}
ROWS = [
    R("處理器 CPU", 11550, "｛AMD R7 9700X｝代理盒裝【8核/16緒】3.8G(↑5.5G)65W /具RDNA內顯"),
    R("處理器 CPU", 15000, "｛AMD R7 9800X3D｝代理盒裝"),
    R("主機板 MB", 7490, "｛技嘉 B850 AORUS ELITE WIFI7｝/ATX/2.5G+Wi-Fi7/註五年/14+2+2相 *優惠至11/30"),
    R("主機板 MB", 7990, "｛技嘉 B850 AORUS ELITE WIFI7 ICE｝/ATX/白"),
    R("記憶體 RAM", 9999, "十銓｛T-CREATE EXPERT 引領者 24G DDR5-6000｝/CL28 黑"),
    R("記憶體 RAM", 19999, "十銓｛T-CREATE EXPERT 48G(24G*2) DDR5-6000｝/CL28 黑"),
    R("固態硬碟 M.2｜SSD", 11000, "｛金士頓 KC3000 2TB｝/Gen4 PCIe 4.0/讀7000/寫7000/TLC【五年保】"),
    R("散熱器｜散熱墊｜散熱膏", 1490, "｛利民 Phantom Spirit 120｝7導管(6mm)/雙塔雙扇/高15.7cm/陽極黑上蓋【WXZ】"),
    R("散熱器｜散熱墊｜散熱膏", 1290, "｛利民 Phantom Spirit 120 SE｝7導管"),
    R("顯示卡VGA", 26590, "｛華碩 PRIME-RTX5060TI-16G｝2602MHz/31cm/三風扇/註冊五年保固"),
    R("顯示卡VGA", 27590, "｛華碩 PRIME-RTX5060TI-O16G｝2647MHz/31cm/三風扇/註冊五年保固"),
    R("CASE 機殼(+電源)", 3590, "Montech Air 903 MAX 黑/玻璃透側/E-ATX+Montech GAMMA 3 750W/金牌/ATX3.1電源！"),
    R("CASE 機殼(+電源)", 3590, "Montech Air 903 MAX 白/玻璃透側/E-ATX+Montech GAMMA 3 750W/金牌/ATX3.1電源！"),
]


class FinalBuildTest(unittest.TestCase):
    def test_matches_quote(self):
        res = match_config(CFG, ROWS)
        self.assertTrue(res["complete"])
        self.assertEqual(res["total"], 71709)
        self.assertEqual(CFG["target_total"], 71709)
        for it in CFG["items"]:
            with self.subTest(slot=it["slot"]):
                self.assertEqual(res["items"][it["slot"]]["price"], it["target_price"])
        self.assertNotIn("ICE", res["items"]["主機板 B850 ELITE"]["name"])
        self.assertNotIn("O16G", res["items"]["顯示卡 5060Ti 16G"]["name"])
        self.assertIn("黑", res["items"]["機殼＋電源"]["name"])

    def entry(self, gpu_price, total):
        e = match_config(CFG, ROWS)
        e["items"]["顯示卡 5060Ti 16G"]["price"] = gpu_price
        e["total"] = total
        return e

    def test_small_drop_below_quote_alerts_as_new_low(self):
        hist = {"2026-11-28": self.entry(26590, 71709), "2026-11-29": self.entry(26390, 71509)}
        a = notify.compute_alerts(CFG, hist, "2026-11-29")
        self.assertTrue(any("顯示卡" in x and "新低" in x for x in a))
        self.assertTrue(any("總價創新低" in x for x in a))

    def test_old_build_totals_ignored(self):
        old = {"items": {}, "total": 60000, "complete": True}          # before build_since
        hist = {"2026-11-20": old, "2026-11-28": self.entry(26590, 71709), "2026-11-29": self.entry(26590, 71600)}
        self.assertTrue(any("總價創新低" in x for x in notify.compute_alerts(CFG, hist, "2026-11-29")))


if __name__ == "__main__":
    unittest.main()
