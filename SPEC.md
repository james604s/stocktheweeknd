stockwatch — 個人美股每日觀測系統規格

版本：v1.2　日期：2026-10-23（v1.1 於 2026-10-16，v1.0 於 2026-10-07）

v1.2 變更：盤中成交量改由 yfinance 提供；量能規則加 basis 欄位；哨兵時段外仍 ping healthchecks。

1. 目標與範圍

目標：一個只給自己用的美股每日觀測系統，每天早上提供一份有解讀的日報，盤中對重大波動推播。

範圍內（v1）
觀察清單的價格與異動
自己持股的損益追蹤
技術指標與狀態變化
新聞與事件摘要
盤中規則推播
Claude 生成的每日解讀
範圍外（明確不做）
任何買賣建議或預測
券商 API 自動下單或自動同步持股
即時 tick 級別資料
多人使用、權限管理
Web UI（階段 6 之前不做；階段 6 以 Streamlit 驗證，見第 12 節）
2. 系統架構

兩條獨立的排程線，共用一個 SQLite 和一組設定檔：

config/*.yaml ──┐
                ├──> jobs/daily.py  (06:00 台灣時間, 交易日隔日)
data/stock.db ──┤      fetch 日線 → 算指標 → 抓新聞 → Claude 解讀 → #daily-report
                │
                └──> jobs/watch.py  (每 5 分鐘, 僅美股盤中)
                       fetch 報價 → 跑規則 → dedupe → #alerts

所有錯誤與心跳 ──> #ops
持股異動 ──> #holdings

執行環境：GCP e2-micro（us-central1）或 Hetzner 美國機房，Ubuntu 24.04，系統時區 UTC，cron 驅動。

3. 技術選型
層	選擇	理由
語言	Python 3.12 + uv	迭代快、生態完整
日線資料	yfinance	免申請、夠用；隔離在介面後面
盤中價格、新聞	Finnhub 免費 tier	有 quote 與 company news，60 req/min
盤中成交量	yfinance 當日日線	Finnhub 免費 quote 不含成交量
儲存	SQLite	單一寫入者、零維運
指標	pandas-ta	常見指標全有
交易日曆	exchange_calendars	處理休市、夏令時間
通知	Discord webhook	免寫 bot、有頻道、embed 可讀
解讀	Claude API（Sonnet）	每日一次，成本可忽略
監控	healthchecks.io 免費方案	dead man's switch
開發	Claude Code	以 CLAUDE.md 約束
4. 目錄結構
stockwatch/
  config/
    watchlist.yaml
    rules.yaml
    transactions.csv
  src/stockwatch/
    datasource/     介面 + yfinance / finnhub 實作
    store/          SQLite schema 與存取
    indicators/     pandas-ta 包裝
    rules/          規則引擎（純函數）+ dedupe
    report/         日報 section 組裝與 Discord embed
    notify/         notify(channel, payload) 介面 + Discord sender
    llm/            Claude API 呼叫
      prompts/      daily_v1.md ...
    calendar.py     per-market 交易日曆與時段判斷
  jobs/
    daily.py
    watch.py
  dashboard/        階段 6：Streamlit app（讀 SQLite，不寫入）
    app.py
    pages/
  tests/
    fixtures/       錄好的 API 回應
  scripts/
    deploy.sh
    backup.sh
  data/             stock.db（不進 git）
  logs/             （不進 git）
  .env.example
  CLAUDE.md
  SPEC.md
5. 資料模型
sql
instruments      (ticker PK, name, market, in_watchlist, added_at)
daily_bars       (ticker, date, open, high, low, close, volume, PK(ticker,date))
quotes           (ticker, ts, price, prev_close, day_volume NULL 可, PK(ticker,ts))
indicators       (ticker, date, rsi14, ma20, ma50, ma200, macd, macd_signal,
                  vol_avg20, PK(ticker,date))
news             (id PK, ticker, published_at, headline, source, url, fetched_at)
transactions     (id PK, date, ticker, side, qty, price, currency, note)
alerts_sent      (ticker, rule_id, date, ts, payload, PK(ticker,rule_id,date))
daily_summaries  (date PK, prompt_version, input_tokens, output_tokens, text)

設計要點：

instruments.market 從第一天就有，v1 只填 US，為台股與加密貨幣留門。
持股不存快照，從 transactions 彙算（qty、均價）；已實現損益以後才算得出。
transactions.currency 從第一天就有；總損益以 TWD 彙總，匯率來源於階段 3.5 決定。
daily_summaries 存 prompt 版本與 token 用量，方便回頭評估解讀品質與成本。
所有寫入 idempotent：upsert 為準，重跑不重複。
不使用 SQLite 專屬語法（為日後換 Postgres 留路）。
6. 設定檔

config/watchlist.yaml

yaml
instruments:
  - {ticker: NVDA, market: US}
  - {ticker: AAPL, market: US}

config/rules.yaml

yaml
rules:
  - id: pct_move_5
    type: pct_change_vs_prev_close
    threshold: 0.05
    channels: [alerts]
  - id: vol_spike_2x
    type: volume_vs_avg20
    multiplier: 2.0
    basis: full_day   # 盤中累積量直接與整日 20 日均量比；之後可加依交易時間換算的基準
    channels: [alerts]

config/transactions.csv（手動維護，日報 job 啟動時同步進 DB）

date,ticker,side,qty,price,currency,note
2026-09-15,NVDA,BUY,10,175.20,USD,initial
2026-09-20,2330.TW,BUY,1000,1050,TWD,initial

.env（不進 git，權限 600）

FINNHUB_KEY=
ANTHROPIC_API_KEY=
DISCORD_WEBHOOK_DAILY=
DISCORD_WEBHOOK_ALERTS=
DISCORD_WEBHOOK_HOLDINGS=
DISCORD_WEBHOOK_OPS=
HEALTHCHECKS_URL_DAILY=
HEALTHCHECKS_URL_WATCH=
7. 日報規格（jobs/daily.py）

觸發：台灣 06:00（cron 0 22 * * * UTC，前一日），程式自行判斷前一日是否美股交易日，否則退出。

流程

同步 transactions.csv → DB，有新增就推 #holdings
抓觀察清單 + 持股所有 ticker 的日線（增量，回補近 5 日防缺漏）
計算指標並寫入 indicators
抓每檔近 24 小時新聞，上限 5 篇
組裝結構化 JSON → 呼叫 Claude → 取得解讀，存 daily_summaries
組 embed → POST #daily-report
ping healthchecks

Embed 區塊順序

今日重點（Claude 產出，≤ 300 字）
持股損益：每檔市值、未實現損益、當日變動；總計一行
觀察清單異動：依當日漲跌幅排序，標註成交量倍數
技術訊號：只列當日「狀態改變」的事件（穿越均線、RSI 進出超買超賣區）
新聞：每檔最多 2 條標題 + 連結

限制：單 embed 6000 字；超過就拆兩則。Claude 失敗時日報照發，重點區塊顯示「解讀暫缺」。

8. 盤中哨兵規格（jobs/watch.py）

觸發：cron */5 * * * *。程式啟動後自行判斷：

今天是否美股交易日
現在是否在 09:30–16:30 ET（含盤後 30 分鐘緩衝），由 exchange_calendars 判斷
不符合直接退出，不打任何資料 API；仍 ping healthchecks，證明 cron 與 VPS 存活

流程

抓觀察清單 + 持股的報價寫入 quotes：價格來自 Finnhub quote，當日累積成交量來自 yfinance 當日日線；成交量取不到時為 NULL，價格規則照常執行
對每檔跑所有規則：rule(ticker, quote, history) -> Optional[AlertPayload]
命中者查 alerts_sent，同 ticker 同規則當日已推則跳過
推 #alerts，寫入 alerts_sent
每整點推心跳到 #ops：「哨兵存活，本輪檢查 N 檔，命中 M 條」
ping healthchecks（寬限 15 分鐘）；本輪報價全數失敗時改 ping /fail，由 healthchecks 通知，不每 5 分鐘推 #ops

Alert 格式：embed 標題 NVDA ▲ +6.2%，顏色漲綠跌紅；欄位：現價、前收、成交量倍數、觸發規則。v1 不呼叫 Claude。

防轟炸：每輪最多推 10 則，超過合併成一則摘要。

規則約束：純函數，不碰 DB、不碰系統時間，只依賴傳入參數，可直接以 daily_bars 回測。history 為報價日之前的日線，不含當日。

量能比較基準（basis）：v1 為 full_day，盤中累積量直接與前 20 個交易日的整日均量比，觸發多半集中在收盤前。日後若改為依已過交易時間換算預期量，需新增 basis 並把「交易時段進度」傳入規則；改動時 2x 門檻需以 alerts_sent 紀錄重新檢討。

9. Claude 解讀規格

輸入：結構化 JSON——每檔漲跌幅、成交量倍數、指標狀態變化、新聞標題列表、持股損益摘要。不餵原始資料。

Prompt 原則（src/stockwatch/llm/prompts/daily_v1.md，版本化）

角色：幫使用者整理「今天值得注意什麼」的分析助理
明確禁止：預測價格、建議買賣、使用「應該」「建議」等字眼
順序：先持股相關、再觀察清單、最後整體；每點附依據（數據或新聞）
長度：300 字內，繁體中文

成本與韌性：Anthropic console 設每月 $5 上限；記錄 token 到 daily_summaries；timeout 30 秒、retry 2 次；失敗不阻擋日報。

10. 營運
Log：logs/daily.log、logs/watch.log，logrotate 保留 14 天
錯誤：job 最外層 try/except，traceback 推 #ops，再 re-raise 讓 cron 記錄非零退出
備份：scripts/backup.sh 每日 sqlite3 .backup 到 backups/，保留 30 份
部署：scripts/deploy.sh = git pull && uv sync；v1 手動，穩定後改 GitHub Actions SSH deploy
外部呼叫：yfinance、Finnhub、Claude、Discord 一律 timeout + 指數退避 retry（3 次）
金鑰：只存 VPS 的 .env
11. 開發流程
每個階段一個 branch、一個 PR，PR 描述對應該階段完成判準
規則引擎與指標計算必須有 pytest；datasource 用 tests/fixtures/ 錄好的回應，不打真實 API
Claude Code 的工作單位：每次指令對應下方時程中的一個步驟
12. 時程與里程碑
階段	內容	完成判準
0 前置	帳號、金鑰、Discord 頻道與 webhook、VPS、初始設定檔	VPS 上 curl 打 webhook，#ops 收到
1 骨架	repo、SPEC.md、CLAUDE.md、目錄、schema	Claude Code 能正確複述專案目標
2 日報 MVP	日線 fetch、純數字日報、cron 部署	連續 3 個交易日自動收到日報
3 哨兵	Finnhub quote、規則引擎、dedupe、心跳、healthchecks	跑滿一週、至少一次真實觸發、零重複
4 大腦	transactions 與損益、指標、新聞、Claude 解讀	日報有五個區塊，解讀有實質內容
5 營運化	log、備份、deploy script、規則檢討	一週不碰它仍每天準時報到
3.5 台股	TWSE/TPEx + FinMind datasource、TW 日曆、幣別、頻道拆分	台股日報與哨兵各跑一週無誤
6 Dashboard 驗證	Streamlit 三頁：損益、日報歷史、規則與警報	連續兩週每週至少打開三次，否則停在這裡

階段順序：0 → 1 → 2 → 3 → 3.5 → 4 → 5 → 6。台股在哨兵穩定後、大腦之前加入，讓階段 4 一開始就是雙市場。

階段 0 細項
Finnhub API key、Anthropic API key（設 $5/月上限）、GCP 帳號
Discord 私人 server，開 #daily-report #alerts #holdings #ops，各建 webhook
GCP e2-micro（us-central1，Ubuntu 24.04），billing alert $1；裝 Python 3.12、git、uv；時區保持 UTC
準備 watchlist.yaml、transactions.csv、rules.yaml 初始內容
階段 2 細項
datasource/：yfinance 抓近 60 天日線，寫入 daily_bars，idempotent
report/：讀 DB 算當日漲跌、20 日均量倍數，組 embed（不呼叫 Claude）
jobs/daily.py 串接 + 交易日判斷
部署到 VPS，crontab 設定，錯誤推 #ops
階段 3 細項
Finnhub quote（價格）+ yfinance 當日成交量 → quotes
rules/：從 rules.yaml 讀規則，純函數，dedupe 查 alerts_sent
jobs/watch.py：啟動判斷交易時段，否則退出
整點心跳 + healthchecks ping
階段 3.5 細項（台股）
新增 datasource/twse.py（上市日線）、datasource/tpex.py（上櫃日線）、datasource/finmind.py（盤中報價）；介面不變
calendar.py 加 TW 分支：交易日曆、09:00–13:30 時段、休市日
transactions.currency 生效；加匯率來源（yfinance TWD=X 日線），總損益以 TWD 彙總
Discord 頻道拆成 #alerts-us、#alerts-tw，notify channel 增加對應值；台股哨兵在上班時間推播，通知等級分開設定
台股日報：14:30 單獨發，或併入隔日 06:00 美股日報——先各跑一週再決定
規則門檻 per-market：台股漲跌幅上限 ±10%，rules.yaml 的 threshold 允許依 market 覆寫
階段 4 細項
transactions.csv → DB，損益計算，#holdings 異動通知
pandas-ta 指標 → indicators，日報只列狀態變化
Finnhub news → news，每檔上限 5 篇
Claude 解讀：daily_v1.md prompt，輸出存 daily_summaries
（關閉狀態）哨兵觸發時呼叫 Claude 附「可能原因」
階段 5 細項
logrotate、backup.sh
deploy.sh，可選 GitHub Actions
以 alerts_sent 紀錄檢討規則門檻
可選：discord.py slash command——三週內沒想用過就不做
階段 6 細項（Dashboard 驗證）
dashboard/app.py：Streamlit，唯讀連 data/stock.db，不經過管線程式碼以外的任何寫入
三頁：損益（持股曲線、每檔報酬率、交易紀錄）、日報歷史（任一天的日報與 Claude 解讀）、規則與警報（每條規則觸發紀錄、可標記誤報）
部署：同一台 VPS 多一個 streamlit run process，透過 Tailscale 或 Cloudflare Tunnel 限自己連線，不開公網 port
驗證兩週：記錄打開次數。沒在看就停在 Streamlit，不往下做
升級 React 的條件（任一成立才啟動，否則永遠停在 Streamlit）
需要手機上順手操作，Streamlit 的 RWD 已經影響使用
出現需要前端狀態的互動：拖拉調整觀察清單、即時更新圖表、多條件篩選聯動
頁面超過五頁，或 Streamlit 整頁重跑的延遲明顯影響使用 啟動時：React + Vite + Tailwind + ECharts，後端補 FastAPI 讀 API；資料管線與 SQLite 不變。
13. 設計約束（為延伸預留）
資料源在介面後面：DataSource.get_daily_bars / get_quote / get_news，yfinance 與 Finnhub 是實作
market 是一等概念：日曆與交易時段 per-market 查表，不寫死 NYSE
持股從交易紀錄推導，不存快照
規則是純函數，可回測
通知走 notify(channel, payload) 介面，Discord 是其中一個 sender
日報由 section 列表組成，新增區塊不動既有程式
14. 風險與對策
風險	對策
yfinance 壞掉	資料源介面隔離；日線 fetch 失敗時以 Finnhub candles 備援
推播轟炸	dedupe + 每輪最多 10 則，超過合併
哨兵默默死掉	healthchecks.io + 整點心跳
Claude 輸出偏離	prompt 版本化、輸出存 DB、失敗不影響日報
VPS 免費方案被收回	每日備份、deploy.sh 讓搬家 30 分鐘內完成
規則誤報太多	alerts_sent 留完整紀錄，階段 5 回測調門檻
15. v2 Backlog（不排程，只記錄）
React dashboard（條件見第 12 節，不主動啟動）
加密貨幣（24h market，無交易時段概念，calendar.py 需支援 always-open）
財報日曆與財報季專用摘要
週報：Claude 雲端排程做一週回顧與規則誤報檢討
discord.py slash command（/pnl、/add、/mute）
規則回測工具與門檻自動建議
