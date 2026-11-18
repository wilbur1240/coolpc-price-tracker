# 原價屋目標配置價格追蹤：腳本版交接說明

給 Claude Code：請讀完這份文件，在這個資料夾建立一個 GitHub repo 專案，實作下面的「目標」。`prototype/` 是在 claude.ai 上做的原型（可沿用、可重寫），`data/` 是目前的設定與第一天的資料。

## 目標
每天自動抓原價屋線上估價（https://www.coolpc.com.tw/evaluate.php）全部價格，算出我目標配置的總價與漲跌，產生一個靜態網頁，並在達到目標價時通知我的手機與電腦。不依賴 Claude 執行，也不需要我的電腦開著。

## 建議架構
- `tracker/`：Python 套件（requests + 標準庫 html.parser 或 lxml/bs4 皆可）
  - `fetch.py`：下載 evaluate.php（Big5／cp950 編碼，設定一般瀏覽器 User-Agent、timeout、重試）。原始 HTML 不必進 repo，可存成 Actions artifact 方便除錯。
  - `parse.py`：解析成 `[{cat, group, name, price}]`，**全部分類都存**（約 30 類、數千筆）。
  - `match.py`：依 `data/config.json` 比對目標品項（規則見下）。
  - `render.py`：產生 `docs/index.html`（或 gh-pages branch）。
  - `notify.py`：通知。
- `data/config.json`：目標配置（已附）。
- `data/history.json` 或 `data/prices/YYYY-MM-DD.json(.gz)`：每日快照。目標品項的歷史一定要保留；全量快照可壓縮或只留最近 N 天，避免 repo 膨脹。
- `.github/workflows/daily.yml`：`cron: '50 1 * * *'`（台北 09:50），跑完把 data 與 docs commit 回 repo；另外加 `workflow_dispatch` 方便手動跑。
- GitHub Pages 發佈 `docs/`。注意免費方案的 Pages 要用 public repo；價格資料是公開的，用 public repo 沒問題。
- 本機執行：`python -m tracker run` 要能在本機跑通（不經 GitHub），方便除錯，也能當備案（cron／systemd timer）。

## 頁面需求
- 摘要：今日總價、較前一次漲跌、目標總價與差距、追蹤以來最低總價、「x/y 已達目標價」
- 目標配置表：每個部件今天最便宜的符合品項、單價、漲跌、歷史最低、目標價（達標標綠色）；`optional` 品項顯示為「升級選項，不計入總價」
- 總價走勢圖，以及每個部件單價的走勢（可點選）
- 今日完整報價表：可搜尋（以空白分隔多個關鍵字）、可篩分類、可依價格排序
- 手機也要好讀；支援亮／暗色

## 通知
- 推薦 ntfy.sh（手機 App 與電腦瀏覽器都能收，免帳號）或 Telegram bot，二選一或兩者都做，用 GitHub Secrets 存 topic／token。
- 規則：有部件「新達到目標價」、或總價創新低、或單一部件漲跌超過 5% 時才發通知；另外可選每日摘要。
- 抓取失敗（HTTP 錯誤、解析出的筆數異常少）也要發通知，不可寫入假資料。

## 原價屋頁面結構（2026-11-18 實測）
- 每個分類是一列 `<tr>`，分類名稱在 `<td class="t">`（第一個 td 只是編號），裡面有 `<select name="n4">` 等，選項可能包在 `<optgroup label=...>` 裡。
- 選項文字範例：`｛Intel Core Ultra 5 245K｝【14核】4.2G..., $6650 ★`；降價時是 `$6990↘$5990`，要取**最後一個** `$數字`。品名常用全形 `｛｝` 包住型號；有些選項是公告（`↪ ...`），沒有價格，要略過。
- 實際分類名：`處理器 CPU`、`主機板 MB`、`記憶體 RAM`、`固態硬碟 M.2｜SSD`、`散熱器｜散熱墊｜散熱膏`、`顯示卡VGA`、`CASE 機殼(+電源)`、`電源供應器`。
- 陷阱：「機殼」也會對到「機殼風扇｜機殼配件」，「電源」也會對到「CASE 機殼(+電源)」，所以 config 用 `CASE`、`電源供應器`。

## 比對規則（config.json）
- `category`：分類名稱的部分字串。
- `match`：所有關鍵字都要出現；`exclude`：任一出現就排除。比對時忽略大小寫與空白（全形空白也算）。
- 有多個符合時取最便宜的，並記下符合的件數。
- `qty`、`target_price`（單價目標）、`target_total`（整台目標）、`optional`（不計入總價）。
- 原價屋寫法跟官方不同的例子：`Pop 2 Air`、`64GB(雙通32GB*2)`、`RTX5060TI-O16G`。
- 找不到符合品項時要顯示「缺項」，該天總價標為不完整，不計入走勢。
- 進階（可選）：支援 `"mode": "cheapest_spec"`，例如 SSD 用「2TB + TLC + Gen4」找同規格最便宜的，取代指定型號。

## 驗收
1. `python -m tracker run` 在本機成功，CPU 分類筆數 > 20，總筆數 > 1000。
2. 用 `data/sample_2026-11-18.txt`（格式 `分類|價格|品名`）寫單元測試：比對結果應為 CPU 11550、GPU 25590、主機板 8390、RAM 29999、SSD 12111、PSU 2390、散熱器 1490、機殼 3690，總價 95,210（5070 Ti 45990 為 optional，不計入）。
3. 第一次在 GitHub Actions 上跑：**先確認 GitHub runner 能不能連到 coolpc.com.tw**（可能擋海外 IP）。如果被擋，改成 self-hosted runner，或在我本機用 cron 跑完再 push，並在 README 寫清楚。
4. README：如何改目標配置、如何手動觸發、如何設定通知、網頁網址。

## 目前狀態
- claude.ai 上已有一個每天 09:50 的 Claude 排程在跑（用 Claude 桌面版的內建瀏覽器抓價格），頁面在 https://claude.ai/artifact/T2M3S5A6YKqvGBLPfGH5Qv。腳本版穩定後再請 Claude 關掉那個排程。
- 2026-11-18 第一筆資料已在 `data/history.json`（格式可以自由改，但請轉換保留這筆）。
