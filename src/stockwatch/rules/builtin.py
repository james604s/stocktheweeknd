"""內建規則。每個工廠函數依 rules.yaml 的參數回傳一個純函數規則。"""

from stockwatch.datasource import DailyBar, Quote
from stockwatch.rules import AlertPayload, Rule

VOL_WINDOW = 20
GREEN = 0x2ECC71
RED = 0xE74C3C
GREY = 0x95A5A6

# 成交量比較基準。full_day：盤中累積量直接與整日 20 日均量比。
# 之後若改依交易時間換算，在這裡新增一種基準即可，不動規則結構。
VOLUME_BASES = ("full_day",)


def pct_change(quote: Quote) -> float | None:
    if quote.prev_close <= 0:
        return None
    return quote.price / quote.prev_close - 1.0


def volume_multiple(quote: Quote, history: list[DailyBar]) -> float | None:
    """盤中累積量 / 前 20 個交易日均量。資料不足時回傳 None。"""
    if quote.day_volume is None or len(history) < VOL_WINDOW:
        return None
    avg = sum(b.volume for b in history[-VOL_WINDOW:]) / VOL_WINDOW
    if avg <= 0:
        return None
    return quote.day_volume / avg


def build_payload(
    ticker: str,
    quote: Quote,
    history: list[DailyBar],
    *,
    rule_id: str,
    channels: tuple[str, ...],
) -> AlertPayload:
    pct = pct_change(quote)
    mult = volume_multiple(quote, history)
    if pct is None:
        arrow, pct_text, color = "─", "n/a", GREY
    else:
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "─"
        pct_text = f"{pct:+.1%}"
        color = GREEN if pct > 0 else RED if pct < 0 else GREY
    return AlertPayload(
        ticker=ticker,
        rule_id=rule_id,
        title=f"{ticker} {arrow} {pct_text}",
        fields={
            "現價": f"{quote.price:,.2f}",
            "前收": f"{quote.prev_close:,.2f}",
            "成交量倍數": f"{mult:.1f}x" if mult is not None else "n/a",
            "觸發規則": rule_id,
        },
        channels=channels,
        color=color,
    )


def pct_change_vs_prev_close(*, rule_id: str, threshold: float, channels: tuple[str, ...]) -> Rule:
    """漲跌幅絕對值 >= threshold（0.05 = 5%）時觸發。"""
    if threshold <= 0:
        raise ValueError(f"{rule_id}: threshold 必須大於 0")

    def rule(ticker: str, quote: Quote, history: list[DailyBar]) -> AlertPayload | None:
        pct = pct_change(quote)
        if pct is None or abs(pct) < threshold:
            return None
        return build_payload(ticker, quote, history, rule_id=rule_id, channels=channels)

    return rule


def volume_vs_avg20(
    *,
    rule_id: str,
    multiplier: float,
    channels: tuple[str, ...],
    basis: str = "full_day",
) -> Rule:
    """盤中累積量 >= 20 日均量 × multiplier 時觸發。"""
    if multiplier <= 0:
        raise ValueError(f"{rule_id}: multiplier 必須大於 0")
    if basis not in VOLUME_BASES:
        raise ValueError(f"{rule_id}: 不支援的 basis {basis!r}，可用：{', '.join(VOLUME_BASES)}")

    def rule(ticker: str, quote: Quote, history: list[DailyBar]) -> AlertPayload | None:
        mult = volume_multiple(quote, history)
        if mult is None or mult < multiplier:
            return None
        return build_payload(ticker, quote, history, rule_id=rule_id, channels=channels)

    return rule
