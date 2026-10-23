"""日報各區塊。每個 section: (DailyContext) -> list[EmbedField]。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from stockwatch.report import EmbedField
from stockwatch.report.stats import TickerStat

FIELD_VALUE_LIMIT = 1024


@dataclass(frozen=True, slots=True)
class DailyContext:
    report_date: date
    stats: list[TickerStat]
    missing: list[str] = field(default_factory=list)  # 當日無資料的 ticker


Section = Callable[[DailyContext], list[EmbedField]]


def chunk_lines(lines: list[str], limit: int = FIELD_VALUE_LIMIT) -> list[str]:
    """把多行文字切成數段，每段長度不超過 limit（Discord field value 上限）。"""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        extra = len(line) + (1 if current else 0)
        if current and size + extra > limit:
            chunks.append("\n".join(current))
            current, size = [], 0
            extra = len(line)
        current.append(line)
        size += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def _fields(name: str, lines: list[str]) -> list[EmbedField]:
    return [
        EmbedField(name=name if i == 0 else f"{name}（續）", value=chunk)
        for i, chunk in enumerate(chunk_lines(lines))
    ]


def format_move(stat: TickerStat) -> str:
    if stat.pct_change is None:
        arrow, pct = "─", "n/a"
    else:
        arrow = "▲" if stat.pct_change > 0 else "▼" if stat.pct_change < 0 else "─"
        pct = f"{stat.pct_change:+.2%}"
    vol = f"量 {stat.vol_multiple:.1f}x" if stat.vol_multiple is not None else "量 n/a"
    return f"{arrow} **{stat.ticker}** {pct}　{stat.close:,.2f}　{vol}"


def watchlist_moves(ctx: DailyContext) -> list[EmbedField]:
    """觀察清單異動：依當日漲跌幅排序，標註成交量倍數。"""
    ordered = sorted(
        ctx.stats,
        key=lambda s: (s.pct_change is None, -(s.pct_change or 0.0)),
    )
    fields: list[EmbedField] = []
    if ordered:
        fields += _fields("觀察清單異動", [format_move(s) for s in ordered])
    else:
        fields.append(EmbedField(name="觀察清單異動", value="（無資料）"))
    if ctx.missing:
        fields += _fields("當日無資料", [", ".join(ctx.missing)])
    return fields


SECTIONS: list[Section] = [watchlist_moves]
