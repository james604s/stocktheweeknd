"""盤中哨兵 job：cron */5 * * * *。

啟動後判斷是否在交易時段（開盤到收盤後 30 分鐘），否則直接退出，不打任何資料 API。
流程見 SPEC.md 第 8 節。最外層 try/except：異常推 #ops 後 re-raise。
"""

import logging
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from stockwatch import calendar as mcal
from stockwatch.config import Settings, load_settings, load_watchlist
from stockwatch.datasource import DataSource
from stockwatch.datasource.finnhub_source import FinnhubSource
from stockwatch.datasource.us import USDataSource
from stockwatch.datasource.yfinance_source import YFinanceSource
from stockwatch.healthcheck import ping
from stockwatch.notify import Channel, configure, notify
from stockwatch.notify.discord import DiscordSender
from stockwatch.report.alerts import plan_messages
from stockwatch.rules import AlertPayload, Rule
from stockwatch.rules.builtin import VOL_WINDOW
from stockwatch.rules.dedupe import select_new
from stockwatch.rules.loader import load_rules
from stockwatch.store import connect, init_schema
from stockwatch.store.alerts import record_alerts, sent_keys
from stockwatch.store.bars import recent_bars
from stockwatch.store.quotes import upsert_quote

log = logging.getLogger("jobs.watch")

MARKET = "US"  # v1 只有美股；階段 3.5 改為依 watchlist 的 market 分組
HEARTBEAT_MINUTES = 5  # 每小時前 5 分鐘內的那一輪推心跳（cron 每 5 分鐘一次）


@dataclass(frozen=True, slots=True)
class WatchResult:
    checked: int
    failed: list[str]
    hits: int
    pushed: int


def run(
    settings: Settings, *, now: datetime, source: DataSource, rules: list[Rule]
) -> WatchResult | None:
    """執行一輪。不在檢查時段時回傳 None。"""
    if not mcal.in_watch_window(MARKET, now):
        log.info("%s 不在盤中檢查時段，退出", MARKET)
        return None

    day = mcal.market_date(MARKET, now)
    history_end = mcal.previous_trading_day(MARKET, day)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    try:
        init_schema(conn)
        tickers = [i.ticker for i in load_watchlist(settings.watchlist_path) if i.market == MARKET]

        hits: list[AlertPayload] = []
        failed: list[str] = []
        for ticker in tickers:
            try:
                quote = source.get_quote(ticker)
            except Exception as exc:
                log.warning("%s 報價失敗：%s", ticker, exc)
                failed.append(ticker)
                continue
            upsert_quote(conn, quote)
            history = recent_bars(conn, ticker, end=history_end, limit=VOL_WINDOW)
            for rule in rules:
                payload = rule(ticker, quote, history)
                if payload is not None:
                    hits.append(payload)

        fresh = select_new(hits, sent_keys(conn, day))
        by_channel: dict[str, list[AlertPayload]] = defaultdict(list)
        for p in fresh:
            for channel in p.channels:
                by_channel[channel].append(p)

        pushed = 0
        for channel, payloads in by_channel.items():
            for message, covered in plan_messages(payloads):
                notify(_channel(channel), message)
                # 每推一則就記錄，避免中途失敗後重跑時重複推送
                record_alerts(conn, covered, day=day, ts=now)
                pushed += 1
    finally:
        conn.close()

    result = WatchResult(checked=len(tickers), failed=failed, hits=len(hits), pushed=pushed)
    log.info(
        "本輪檢查 %d 檔，失敗 %d 檔，命中 %d 條，推送 %d 則",
        result.checked,
        len(failed),
        result.hits,
        result.pushed,
    )

    if now.minute < HEARTBEAT_MINUTES:
        notify("ops", {"content": heartbeat_text(result)})
    return result


def _channel(name: str) -> Channel:
    if name not in ("daily", "alerts", "holdings", "ops"):
        raise ValueError(f"未知頻道 {name}")
    return name  # type: ignore[return-value]


def heartbeat_text(result: WatchResult) -> str:
    text = f"💓 哨兵存活，本輪檢查 {result.checked} 檔，命中 {result.hits} 條"
    if result.pushed:
        text += f"，新推送 {result.pushed} 則"
    if result.failed:
        names = "、".join(result.failed[:10])
        more = f" 等 {len(result.failed)} 檔" if len(result.failed) > 10 else ""
        text += f"\n⚠️ 報價失敗：{names}{more}"
    return text


def _report_failure(tb: str) -> None:
    try:
        notify("ops", {"content": f"❌ watch job 失敗\n```\n{tb[-1800:]}\n```"})
    except Exception:
        log.exception("推送 #ops 失敗")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    settings: Settings | None = None
    try:
        settings = load_settings()
        configure(DiscordSender(settings.discord_webhooks))
        rules = load_rules(settings.rules_path)
        now = datetime.now(UTC)
        if not mcal.in_watch_window(MARKET, now):
            # 時段外不建立資料源、不打資料 API，只 ping healthchecks 證明 cron 還在跑
            log.info("%s 不在盤中檢查時段，退出", MARKET)
            result = None
        else:
            source = USDataSource(FinnhubSource(settings.finnhub_key or ""), YFinanceSource())
            result = run(settings, now=now, source=source, rules=rules)
    except Exception:
        log.exception("watch job 失敗")
        _report_failure(traceback.format_exc())
        if settings is not None and settings.healthchecks_watch:
            ping(settings.healthchecks_watch, fail=True)
        raise

    if settings.healthchecks_watch:
        all_failed = (
            result is not None and result.checked > 0 and len(result.failed) == result.checked
        )
        # 報價全數失敗時 ping /fail，由 healthchecks 通知一次，避免每 5 分鐘洗版 #ops
        ping(settings.healthchecks_watch, fail=all_failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
