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

**連線實測（2026-11-18）**：GitHub-hosted runner（ubuntu-latest）可以正常連到 coolpc.com.tw，解析出 6,586 筆、30 類，所以不需要 self-hosted runner。如果之後被擋，改用下面的「備案：本機 cron」。

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

在本機設好環境變數後執行 `python -m tracker notify-test`。如果要測 Actions 上的設定，手動觸發一次 workflow，再看 log 裡的 `[notify]` 行。

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

### 備案：本機 cron

如果 GitHub runner 被原價屋擋掉，可以改在本機（或任何台灣 IP 的機器）跑 `scripts/local_run.sh`。它會 pull、執行、commit 並 push，網頁照樣由 GitHub Pages 發佈。通知用的 secret 寫在 `scripts/.env`（已加入 gitignore）。

```cron
50 9 * * * /path/to/coolpc-price-tracker/scripts/local_run.sh >> /tmp/coolpc.log 2>&1
```

本機 cron 用的是本機時區，上面這行假設本機是台北時間。改用本機跑時，記得把 `daily.yml` 的 `schedule` 拿掉，避免兩邊同時寫入。

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
