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
```

先用 `command -v uv` 確認 uv 的實際位置；若不在 `~/.local/bin`，改成對應路徑。
可用 cron 的環境驗證一次：

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin sh -c 'cd $HOME/stockwatch && $HOME/.local/bin/uv run python jobs/daily.py'
```

- 執行失敗時 traceback 會推到 #ops，並以非零退出讓 cron 記錄。
- 設定 `HEALTHCHECKS_URL_DAILY` 後，每次成功執行會 ping 一次（含非交易日）；失敗 ping `/fail`。
- 單檔抓取失敗不會擋住日報：該檔列入「當日無資料」，錯誤摘要另推 #ops。

## 階段進度

| 階段 | 狀態 |
|---|---|
| 1 骨架 | 完成 |
| 2 日報 MVP（純數字日報、cron 部署） | 程式完成，待 VPS 連續 3 個交易日驗證 |
