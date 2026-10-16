"""日報 job：cron 0 22 * * * UTC（台灣 06:00）。

程式自行判斷當地日期是否為已收盤的交易日，否則退出。
流程見 SPEC.md 第 7 節；階段 2 只做純數字日報（不呼叫 Claude）。
最外層 try/except：異常推 #ops 後 re-raise，讓 cron 記錄非零退出。
"""

import logging
import sys
import traceback
from datetime import UTC, datetime, timedelta

from stockwatch import calendar as mcal
from stockwatch.config import Settings, load_settings, load_watchlist
from stockwatch.datasource import DataSource
from stockwatch.datasource.yfinance_source import YFinanceSource
from stockwatch.healthcheck import ping
from stockwatch.notify import configure, notify
from stockwatch.notify.discord import DiscordSender
from stockwatch.report.embed import build_embeds
from stockwatch.report.sections import DailyContext
from stockwatch.report.stats import VOL_WINDOW, TickerStat, compute_stat
from stockwatch.store import connect, init_schema
from stockwatch.store.bars import latest_bar_date, recent_bars, upsert_daily_bars
from stockwatch.store.instruments import sync_watchlist

log = logging.getLogger("jobs.daily")

MARKET = "US"  # v1 只有美股；階段 3.5 改為依 watchlist 的 market 分組
INITIAL_DAYS = 60  # 首次抓取回看天數
BACKFILL_DAYS = 5  # 增量抓取回補天數，防缺漏


def run(settings: Settings, *, now: datetime, source: DataSource) -> bool:
    """執行一次日報。回傳是否有發送（非交易日回傳 False）。"""
    report_date = mcal.completed_session(MARKET, now)
    if report_date is None:
        log.info("%s 當地 %s 非交易日或尚未收盤，退出", MARKET, mcal.market_date(MARKET, now))
        return False
    log.info("日報日期 %s", report_date)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_schema(conn)

    watchlist = [i for i in load_watchlist(settings.watchlist_path) if i.market == MARKET]
    sync_watchlist(conn, watchlist, now=now)

    stats: list[TickerStat] = []
    missing: list[str] = []
    failed: dict[str, str] = {}
    for inst in watchlist:
        try:
            latest = latest_bar_date(conn, inst.ticker)
            start = (
                latest - timedelta(days=BACKFILL_DAYS)
                if latest
                else report_date - timedelta(days=INITIAL_DAYS)
            )
            upsert_daily_bars(conn, source.get_daily_bars(inst.ticker, start, report_date))
        except Exception as exc:
            log.exception("%s 日線抓取失敗", inst.ticker)
            failed[inst.ticker] = f"{type(exc).__name__}: {exc}"
        history = recent_bars(conn, inst.ticker, end=report_date, limit=VOL_WINDOW + 1)
        stat = compute_stat(inst.ticker, history, report_date)
        if stat is None:
            missing.append(inst.ticker)
        else:
            stats.append(stat)

    ctx = DailyContext(report_date=report_date, stats=stats, missing=missing)
    for embed in build_embeds(ctx, generated_at=now):
        notify("daily", {"embeds": [embed]})

    if failed:
        lines = "\n".join(f"- {t}: {msg}" for t, msg in failed.items())
        notify("ops", {"content": f"⚠️ 日報 {report_date} 有 {len(failed)} 檔抓取失敗\n{lines}"})
    return True


def _report_failure(tb: str) -> None:
    body = tb[-1800:]
    try:
        notify("ops", {"content": f"❌ daily job 失敗\n```\n{body}\n```"})
    except Exception:
        log.exception("推送 #ops 失敗")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    settings = load_settings()
    configure(DiscordSender(settings.discord_webhooks))
    now = datetime.now(UTC)
    try:
        run(settings, now=now, source=YFinanceSource())
    except Exception:
        log.exception("daily job 失敗")
        _report_failure(traceback.format_exc())
        if settings.healthchecks_daily:
            ping(settings.healthchecks_daily, fail=True)
        raise
    if settings.healthchecks_daily:
        ping(settings.healthchecks_daily)
    return 0


if __name__ == "__main__":
    sys.exit(main())
