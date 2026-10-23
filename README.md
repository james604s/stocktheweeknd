# stockwatch

個人用美股每日觀測系統：每天早上一份日報，盤中對重大波動推 Discord。
規格見 [SPEC.md](SPEC.md)，開發守則見 [CLAUDE.md](CLAUDE.md)。

## 本機開發

```bash
uv sync                 # Python 3.12，依 .python-version
uv run ruff check .
uv run pytest
```

測試不打任何外部 API；datasource 用 `tests/fixtures/` 的錄製回應。

## 金鑰保護

金鑰只放 VPS 的 `.env`（權限 600），不進 git。clone 後先啟用 pre-commit hook：

```bash
git config core.hooksPath .githooks
```

- hook 會在每次 commit 前掃描暫存檔，發現 Discord webhook、Anthropic key、healthchecks URL、
  `.env` 金鑰賦值，或 `.env`、`data/`、`logs/`、`*.db` 等檔案就擋下。
- 手動掃描整個 repo：`python3 scripts/check_secrets.py`。pytest 也會跑同一個檢查。
- `.env` 權限比 600 寬時，job 啟動會記 warning。
- 程式不會把 webhook 或 healthchecks URL 寫進 log 或推到 #ops。

## 部署（VPS，Ubuntu 24.04，系統時區 UTC）

```bash
git clone <repo> ~/stockwatch && cd ~/stockwatch
uv sync --no-dev
cp .env.example .env && chmod 600 .env   # 填入 webhook 與金鑰
mkdir -p data logs
```

手動跑一次日報（非交易日或尚未收盤會直接退出，不打 API）：

```bash
uv run python jobs/daily.py
```

crontab（`crontab -e`）：

```cron
# 日報：台灣 06:00 = 前一日 22:00 UTC；程式自行判斷美股是否已收盤
# cron 的 PATH 只有 /usr/bin:/bin，uv 必須寫絕對路徑
0 22 * * * cd $HOME/stockwatch && $HOME/.local/bin/uv run python jobs/daily.py >> logs/daily.log 2>&1
# 盤中哨兵：每 5 分鐘，程式自行判斷是否在美股開盤到收盤後 30 分鐘之間
*/5 * * * * cd $HOME/stockwatch && $HOME/.local/bin/uv run python jobs/watch.py >> logs/watch.log 2>&1
```

先用 `command -v uv` 確認 uv 的實際位置；若不在 `~/.local/bin`，改成對應路徑。
可用 cron 的環境驗證一次：

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin sh -c 'cd $HOME/stockwatch && $HOME/.local/bin/uv run python jobs/daily.py'
```

- 執行失敗時 traceback 會推到 #ops，並以非零退出讓 cron 記錄。
- 設定 `HEALTHCHECKS_URL_DAILY` 後，每次成功執行會 ping 一次（含非交易日）；失敗 ping `/fail`。
- 單檔抓取失敗不會擋住日報：該檔列入「當日無資料」，錯誤摘要另推 #ops。
- 偵測到歷史價格被改寫（股票分割）時，該檔整段重抓並推 #ops 通知。
- 哨兵需要 `.env` 的 `FINNHUB_KEY` 與 `DISCORD_WEBHOOK_ALERTS`。時段外不打資料 API，只 ping
  `HEALTHCHECKS_URL_WATCH`；healthchecks 的寬限時間設 15 分鐘。
- 哨兵每小時第一輪推心跳到 #ops。報價全數失敗時 ping `/fail`，由 healthchecks 通知。
- 規則在 `config/rules.yaml`，同一檔同一規則每天只推一次，每輪最多 10 則。

## 階段進度

| 階段 | 狀態 |
|---|---|
| 1 骨架 | 完成 |
| 2 日報 MVP（純數字日報、cron 部署） | 程式完成，待 VPS 連續 3 個交易日驗證 |
| 3 哨兵（Finnhub 報價、規則引擎、dedupe、心跳） | 程式完成，待 VPS 跑滿一週驗證 |
