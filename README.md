# 原價屋目標配置價格追蹤

每天自動抓 [原價屋線上估價](https://www.coolpc.com.tw/evaluate.php) 的全部報價（約 30 類、6,000 多筆），算出目標配置的總價與漲跌，產生靜態網頁，達到條件時推播到手機和電腦。

**網頁：<https://wilbur1240.github.io/coolpc-price-tracker/>**

## 運作方式

| 時間 | 動作 |
|---|---|
| 每天台北時間 09:50 | GitHub Actions（`.github/workflows/daily.yml`）執行 `python -m tracker run` |
| | 抓 evaluate.php → 解析全部分類 → 依 `data/config.json` 比對目標品項 |
| | 更新 `data/history.json`、存全量快照 `data/prices/YYYY-MM-DD.json.gz`（保留最近 45 天） |
| | 產生 `docs/index.html`，commit 回 repo，GitHub Pages 自動發佈 |
| | 符合通知規則時發 ntfy／Telegram |

GitHub 的排程 cron 常延遲 5～30 分鐘，這是正常現象。

**連線實測（2026-11-18）**：GitHub-hosted runner（ubuntu-latest）可以正常連到 coolpc.com.tw，解析出 6,586 筆、30 類，所以不需要 self-hosted runner。如果之後被擋，改用下面的「備案：整個改在本機跑」。

## 修改目標配置

編輯 `data/config.json`，commit 後下一次執行就會生效（想立刻看結果就手動觸發一次）。

```jsonc
{
  "build_name": "Robotics Development Workstation",
  "target_total": 63500,                 // 整台目標價
  "watch_categories": ["CPU", "顯示卡"],   // 頁面摘要用的分類（部分字串）
  "notify": { "daily_summary": false },  // true = 沒有警示也每天發一則摘要
  "items": [
    {
      "slot": "GPU",                     // 顯示名稱，也是歷史紀錄的 key（改名會斷歷史）
      "category": "顯示卡",               // 分類名稱的部分字串
      "match": ["5060Ti", "16G"],        // 全部都要出現
      "exclude": ["拆封", "福利"],         // 任一出現就排除
      "qty": 1,
      "target_price": 22000,             // 單價目標
      "optional": false                  // true = 升級選項，不計入總價
    }
  ]
}
```

比對時會忽略大小寫、半形／全形與所有空白，所以 `PhantomSpirit120` 也對得到 `Phantom Spirit 120`。有多個符合時取最便宜的那個。

- **分類陷阱**：「機殼」也會對到「機殼風扇｜機殼配件」，「電源」也會對到「CASE 機殼(+電源)」，所以要寫 `CASE`、`電源供應器`。
- **原價屋的寫法**跟官方不一樣，例如 `Pop 2 Air`、`64GB(雙通32GB*2)`、`RTX5060TI-O16G`。不確定的話，先到網頁的「今日完整報價」搜尋看看。
- **用規格找最便宜的**：`match` 不一定要寫型號，例如 SSD 可以寫 `["2TB", "TLC", "Gen4"]`，就會挑同規格裡最便宜的。
- 找不到符合品項時，該部件顯示「缺項」，當天總價標為不完整，不計入總價走勢。

## 連鎖賣場比價（Robotics PC）

除了原價屋，配置裡每個部件也會到 **順發、PChome 24h、欣亞** 搜尋同款，網頁「連鎖賣場比價」表會列出各家價格：綠色是該部件有貨的最低價，另外會算出各家整台總價，以及各通路最低組合總價。

```jsonc
"items": [{
  "slot": "RAM 64GB",
  "match": ["64G", "*2"], ...,              // 原價屋用的規則
  "search": {"*": "DDR5 64G", "sinya": "64G"},  // 各通路的搜尋關鍵字（"*" 是預設）
  "chain_match": ["64G", ["*2", "x2", "2x", "雙通"]],  // 其他通路用的比對規則；內層陣列是「任一符合」
  "chain_exclude": ["D4", "SODIMM"]       // 在 exclude 之外再排除
}],
"chains": {
  "stores": [{"name": "順發", "type": "sunfar"}, {"name": "PChome 24h", "type": "pchome"}, {"name": "欣亞", "type": "sinya"}],
  "exclude": ["平台", "(DIY)", "電競電腦", ...],  // 濾掉整機
  "ratio": [0.5, 2.0]                     // 只接受原價屋價格 0.5～2 倍之間的商品，避免對到配件或整機
}
```

- **欣亞的搜尋**是「任一關鍵字符合」，而且只回傳前 20 筆，所以要給它一個最有辨識度的單字，例如 `TOMAHAWK`、`SN850X`。
- **順發擋海外連線**（2026-11-25 實測：GitHub runner 連線逾時，台灣 IP 正常），所以設了 `"local_only": true`：GitHub 每日執行時會略過，只有在台灣 IP 執行 `scripts/local_run.sh` 時才會更新。網頁會顯示最近一次抓到的價格，標成「MM-DD 舊價」，不計入總價和通知。同樣的設定也用在 3D列印基地站（對 GitHub 回 HTTP 202 驗證頁）。
- **順發**的商品有「能否線上購買」的旗標。不能買的（停產完售、缺貨暫停銷售、限門市購買）會顯示「缺貨」，不計入總價和通知；它們的標價常常是很久以前的舊價。
- **燦坤、NOVA 沒有納入**：燦坤主要賣整機，零組件很少，而且搜尋結果要用瀏覽器執行 JavaScript 才會出現；NOVA 資訊廣場是獨立店家組成的實體商場，沒有統一的線上售價。
- **通知**：某個部件在連鎖賣場**新達到目標價**，而且比原價屋便宜時，會發通知。每日摘要會附上各通路最低組合總價。
- 用 `--skip-chains` 可以略過這一步。

## 其他追蹤商品（多通路比價）

除了原價屋配置，`config.json` 的 `products` 可以追蹤其他商品在多個通路的價格，目前有 Bambu Lab P2S 和 ELEGOO Centauri Carbon 2（都只追單機，不含 Combo）。網頁會多一個「其他追蹤商品」區塊，顯示今日最低價、漲跌、目標價、各通路報價，以及最低價走勢。CC2 沒有設目標價，想設的話在 `target_price` 填數字。

```jsonc
"products": [{
  "slot": "Bambu Lab P2S",
  "target_price": 20000,
  "match": ["P2S"],                    // 通路商品名稱必須包含
  "exclude": ["噴嘴", "二手", ...],     // 配件、二手等排除
  "variant_exclude": ["Combo"],        // 排除 Combo 款式（只追蹤單機）
  "price_min": 12000, "price_max": 30000,  // 價格合理範圍，用來濾掉配件和 Combo
  "sources": [ ... ]
}]
```

| 來源類型 | 說明 |
|---|---|
| `shopify` | Shopify 商店的商品頁（讀 `<網址>.js`），例如 3DMart 台灣總代理 |
| `cyberbiz` | Cyberbiz 商店的商品頁（讀 `<網址>.json`），例如 Kidendesign、天馬科技 |
| `woocommerce` | WooCommerce 商店的商品頁（讀款式資料或 JSON-LD），例如 3D列印基地站 |
| `biggo` | BigGo 比價搜尋，只保留 `stores` 裡列出的主要通路（momo、Coupang、蝦皮商城、PChome、萬家福、順發、燦坤、Yahoo），每個通路取最便宜的一筆 |
| `bambu_store` | Bambu Lab 官方商店（美元標價），用匯率換算成台幣；設 `reference_only`，只列出參考、不計入最低價。**GitHub runner 在美國，會被導到美國官網、拿不到台灣價格**，所以預設沒有啟用，只適合在台灣 IP 的機器上跑 |

- **最低價**：只從有貨的通路中挑選。如果全部缺貨，就取最便宜的那筆並標示「缺貨」。
- **各來源在不同 IP 的狀況不同**（2026-11-21 實測）：3DMart 擋台灣家用 IP（429）但 GitHub runner 可以抓；BigGo 在 runner 上偶爾回 429，程式會等 20～40 秒再重試。
- **momo、Coupang 直接連會被擋**（HTTP 403），所以透過 BigGo 取得它們的價格。BigGo 的資料可能比通路頁面晚幾小時更新。
- **單一來源失敗**不會中斷整次執行，網頁會列出哪些來源失敗。只有全部來源都失敗時才會發通知。
- **通知規則**：新達到目標價、最低價較前一次漲跌 ≥ 5%、創追蹤以來新低。每日摘要也會附上最低價。

## 手動觸發

- 網頁：repo → **Actions** → **daily price check** → **Run workflow**
- CLI：

```bash
gh workflow run daily.yml -R wilbur1240/coolpc-price-tracker
```

## 通知設定

到 repo 的 **Settings → Secrets and variables → Actions → New repository secret** 新增下面的 secret。兩種通知可以二選一，也可以都設。

### ntfy.sh（推薦，免帳號）

1. 想一個不容易被猜到的 topic 名稱，例如 `coolpc-wilbur-8f3k2q`。任何知道 topic 的人都能看到訊息，所以不要用太簡單的名字。
2. 手機裝 ntfy App（iOS／Android）並訂閱這個 topic；電腦開 `https://ntfy.sh/<topic>`，允許瀏覽器通知。
3. 新增 secret `NTFY_TOPIC` = 你的 topic。如果是自架伺服器或受保護的 topic，另外設 `NTFY_SERVER`、`NTFY_TOKEN`。

### Telegram bot

1. 找 @BotFather 建立 bot，取得 token。
2. 先傳一則訊息給你的 bot，再打開 `https://api.telegram.org/bot<token>/getUpdates`，找到 `chat.id`。
3. 新增 secret `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。

### 測試

- Actions 上：**Actions → daily price check → Run workflow**，勾選「只發一則測試通知」。這樣只會發通知，不會抓價格。也可以用 CLI：`gh workflow run daily.yml -f notify_test=true`
- 本機：設好環境變數後執行 `python -m tracker notify-test`

### 通知規則

- 有部件**新達到**目標價（前一次還沒達標，或前一次缺項）
- 總價創追蹤以來新低（只算完整的日子）
- 單一部件較前一次漲跌 ≥ 5%
- 原本有的部件今天變成缺項
- **抓取失敗**（HTTP 錯誤、解析出的筆數 < 1000，或某個需要的分類幾乎沒資料）：發高優先通知，**不寫入任何資料**，workflow 標為失敗
- 同一天重跑、警示內容相同時不會重複發送
- 可選：`config.json` 設 `"notify": {"daily_summary": true}`，沒有警示時也每天發一則摘要

## 本機執行

```bash
pip install -r requirements.txt
python -m tracker run --no-notify      # 抓取 → 寫入 data/ 和 docs/
python -m tracker run --dry-run        # 只印結果，不寫檔
python -m tracker run --input saved.html   # 用存下來的 HTML 重跑
python -m tracker render               # 用現有資料重新產生網頁
python -m unittest -v                  # 單元測試（用 data/sample_2026-11-18.txt）
```

### 在台灣 IP 補抓順發等商店（手動）

順發、3D列印基地站擋海外連線，GitHub 每日執行抓不到（config 裡標了 `"local_only": true`）。想看它們的最新價格時，在自己的電腦上執行：

```bash
scripts/local_run.sh
```

它會 pull、只抓這幾家，併入今天 GitHub 跑出來的資料（其他來源不動）、重新產生網頁，然後 commit 並 push。所以要在當天 GitHub 跑完之後（台北 10 點後）再執行。只想看結果、不寫檔：`python3 -m tracker local --dry-run --no-notify`。

- 某部件在順發新達到目標價時也會發通知；要收到的話，把 Telegram／ntfy 的設定寫在 `scripts/.env`（已加入 gitignore）。
- 不要短時間內重複執行很多次：2026-11-25 測試時連續請求四十多次後，順發開始對這台電腦連線逾時。

### 備案：整個改在本機跑

如果 GitHub runner 連原價屋也被擋，改用 `scripts/local_run.sh --full` 在台灣 IP 的機器跑完整流程，並把 `daily.yml` 的 `schedule` 拿掉，避免兩邊同時寫入。想排程的話可以用 cron 或 Windows 工作排程器；注意 WSL 裡的 cron 只有在 WSL 開著時才會執行。

## 專案結構

```
tracker/
  fetch.py     下載 evaluate.php（cp950，瀏覽器 UA、timeout、重試）
  parse.py     解析成 [{cat, group, name, price}]（處理沒有結尾標籤的 <TD>/<OPTION>、↘ 降價、公告選項）
  match.py     依 config 比對目標品項
  store.py     history.json 與每日快照
  render.py    產生 docs/index.html（template.html + 內嵌資料）
  notify.py    通知規則 + ntfy / Telegram
data/
  config.json  目標配置
  history.json 每天的目標品項價格（永久保留）
  prices/      全量快照 .json.gz（保留最近 45 天）
docs/          GitHub Pages
prototype/     claude.ai 上做的原型（僅供參考）
```

## 原價屋頁面結構備忘（2026-11-18）

- 每個分類是一列 `<TR>`，分類名稱在 `<TD class=t>`，**沒有** `</TD>`；後面接著 `<SELECT name=nX>`，選項可能包在 `<OPTGROUP LABEL=...>` 裡。
- 同一列還有一個「數量」`<SELECT>`，裡面的選項沒有 `</OPTION>`、也沒有價格，解析時會略過。
- 價格在選項文字的最後：`..., $6650 ★`；降價時寫成 `$6990↘$5990`，取最後一個。
- `disabled` 的選項是公告（`↪ ...`），文字裡可能出現「價值 $8,500」，一律略過。
