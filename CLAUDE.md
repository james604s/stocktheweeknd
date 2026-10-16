CLAUDE.md — stockwatch 開發守則

完整規格在 SPEC.md，本檔只放你每次工作都要遵守的事。衝突時以 SPEC.md 為準。

專案一句話

個人用美股觀測系統：每天早上一份有解讀的日報，盤中對重大波動推 Discord。Python + SQLite + cron + Discord webhook，跑在一台 VPS 上。

絕對不做
不產生任何買賣建議或價格預測，程式碼、prompt、文件都不行
不接券商 API
階段 6 之前不做任何 Web UI；階段 6 只用 Streamlit，不引入 node 工具鏈。React 只在 SPEC.md 第 12 節列出的條件成立時才啟動
不寫 SQLite 專屬語法（INSERT OR REPLACE 可用，但封裝在 store/ 內）
不把金鑰、data/、logs/ 進 git
工作方式
一次只做 SPEC.md 第 12 節中的一個編號步驟，做完停下來回報，不要順手做下一步
每個階段一個 branch，命名 phase-N-<slug>
改動前先讀相關模組既有程式，沿用既有命名與結構
不確定規格時問，不要猜
架構約束（違反即重做）
所有外部資料存取走 datasource/ 的介面：get_daily_bars(ticker, start, end)、get_quote(ticker)、get_news(ticker, since)。業務邏輯不得直接 import yfinance 或打 Finnhub。
market 是 instruments 的欄位，交易日曆與時段判斷集中在 calendar.py，依 market 查表。不得在其他地方寫死 NYSE 或美東時間。v1 只有 US，階段 3.5 加 TW。
持股由 transactions 彙算，不得存快照；每筆交易帶 currency，總損益以 TWD 彙總。
規則是純函數：rule(ticker, quote, history) -> Optional[AlertPayload]。不碰 DB、不讀系統時間、不發通知。
通知只透過 notify(channel, payload)，channel 是 daily | alerts | holdings | ops。
日報由 section 列表組成，每個 section 是獨立函數回傳 embed field(s)。
工程規範
所有外部呼叫（yfinance、Finnhub、Claude、Discord、healthchecks）必須有 timeout 與指數退避 retry（3 次）
所有 DB 寫入必須 idempotent，重跑同一天不得產生重複列
job 最外層 try/except：異常推 #ops 後 re-raise
rules/ 與 indicators/ 必須有 pytest；datasource/ 用 tests/fixtures/ 的錄製回應測試，測試不得打真實 API
型別標註、ruff 通過
時間一律 UTC aware datetime 存 DB，顯示時再轉台灣時間
Claude API 使用
只在 llm/ 內呼叫，prompt 放 llm/prompts/，檔名帶版本
輸入是結構化 JSON，不餵原始資料
失敗不得阻擋日報發送
記錄 prompt 版本與 token 用量到 daily_summaries
目錄
config/           watchlist.yaml, rules.yaml, transactions.csv
src/stockwatch/   datasource/ store/ indicators/ rules/ report/ notify/ llm/ calendar.py
jobs/             daily.py, watch.py
dashboard/        階段 6 的 Streamlit app，唯讀 SQLite
tests/            fixtures/
scripts/          deploy.sh, backup.sh
完成判準

每個步驟的「做完」定義在 SPEC.md 第 12 節。達不到判準不算完成。
