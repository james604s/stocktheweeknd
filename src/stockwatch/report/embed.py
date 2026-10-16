"""把 section 產出的 fields 組成 Discord embed，超過 6000 字就拆成多則。"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from stockwatch.report import EmbedField
from stockwatch.report.sections import SECTIONS, DailyContext, Section

EMBED_TOTAL_LIMIT = 6000
EMBED_MAX_FIELDS = 25
COLOR = 0x5865F2
TAIPEI = ZoneInfo("Asia/Taipei")


def _new_embed(title: str, footer: str) -> dict[str, Any]:
    return {"title": title, "color": COLOR, "fields": [], "footer": {"text": footer}}


def embed_size(embed: dict[str, Any]) -> int:
    size = len(embed.get("title", "")) + len(embed.get("description", ""))
    size += len(embed.get("footer", {}).get("text", ""))
    for f in embed.get("fields", []):
        size += len(f["name"]) + len(f["value"])
    return size


def build_embeds(
    ctx: DailyContext,
    *,
    generated_at: datetime,
    sections: list[Section] | None = None,
) -> list[dict[str, Any]]:
    """回傳一至多個 embed dict（Discord webhook 格式）。"""
    fields: list[EmbedField] = []
    for section in sections if sections is not None else SECTIONS:
        fields.extend(section(ctx))

    title = f"stockwatch 日報 {ctx.report_date:%Y-%m-%d}（美股）"
    footer = f"產生於 {generated_at.astimezone(TAIPEI):%Y-%m-%d %H:%M} 台灣時間"

    embeds: list[dict[str, Any]] = [_new_embed(title, footer)]
    for f in fields:
        item = {"name": f.name, "value": f.value, "inline": f.inline}
        current = embeds[-1]
        too_big = embed_size(current) + len(f.name) + len(f.value) > EMBED_TOTAL_LIMIT
        too_many = len(current["fields"]) >= EMBED_MAX_FIELDS
        if current["fields"] and (too_big or too_many):
            current = _new_embed(f"{title}（續）", footer)
            embeds.append(current)
        current["fields"].append(item)
    return embeds
