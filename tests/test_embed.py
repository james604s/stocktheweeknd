from datetime import UTC, date, datetime

from stockwatch.report import EmbedField
from stockwatch.report.embed import EMBED_TOTAL_LIMIT, build_embeds, embed_size
from stockwatch.report.sections import DailyContext, chunk_lines, watchlist_moves
from stockwatch.report.stats import TickerStat

NOW = datetime(2026, 10, 16, 22, 0, tzinfo=UTC)


def _stat(ticker: str, pct: float | None, mult: float | None = 1.0) -> TickerStat:
    return TickerStat(ticker, date(2026, 10, 16), 100.0, 95.0, pct, 1000, 1000.0, mult)


def test_chunk_lines_respects_limit():
    lines = ["x" * 400] * 5
    chunks = chunk_lines(lines, limit=1024)
    assert [len(c) for c in chunks] == [801, 801, 400]
    assert all(len(c) <= 1024 for c in chunks)


def test_watchlist_moves_sorted_by_pct_desc_with_none_last():
    ctx = DailyContext(
        report_date=date(2026, 10, 16),
        stats=[_stat("A", -0.02), _stat("B", None, None), _stat("C", 0.05, 2.5)],
        missing=["ZZZ"],
    )
    fields = watchlist_moves(ctx)
    assert fields[0].name == "觀察清單異動"
    lines = fields[0].value.split("\n")
    assert lines[0].startswith("▲ **C** +5.00%")
    assert "量 2.5x" in lines[0]
    assert lines[1].startswith("▼ **A** -2.00%")
    assert lines[2].startswith("─ **B** n/a")
    assert fields[-1].name == "當日無資料"
    assert fields[-1].value == "ZZZ"


def test_build_embeds_single_embed():
    ctx = DailyContext(report_date=date(2026, 10, 16), stats=[_stat("A", 0.01)])
    embeds = build_embeds(ctx, generated_at=NOW)
    assert len(embeds) == 1
    assert embeds[0]["title"] == "stockwatch 日報 2026-10-16（美股）"
    assert embeds[0]["footer"]["text"] == "產生於 2026-10-17 06:00 台灣時間"
    assert embeds[0]["fields"][0]["name"] == "觀察清單異動"


def test_build_embeds_splits_over_6000_chars():
    def big_section(ctx: DailyContext) -> list[EmbedField]:
        return [EmbedField(name=f"f{i}", value="x" * 1000) for i in range(8)]

    ctx = DailyContext(report_date=date(2026, 10, 16), stats=[])
    embeds = build_embeds(ctx, generated_at=NOW, sections=[big_section])
    assert len(embeds) == 2
    assert all(embed_size(e) <= EMBED_TOTAL_LIMIT for e in embeds)
    assert embeds[1]["title"].endswith("（續）")
    assert sum(len(e["fields"]) for e in embeds) == 8


def test_build_embeds_splits_over_25_fields():
    def many(ctx: DailyContext) -> list[EmbedField]:
        return [EmbedField(name=f"f{i}", value="v") for i in range(30)]

    ctx = DailyContext(report_date=date(2026, 10, 16), stats=[])
    embeds = build_embeds(ctx, generated_at=NOW, sections=[many])
    assert [len(e["fields"]) for e in embeds] == [25, 5]
