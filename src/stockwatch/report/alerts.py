"""盤中警報的 Discord 訊息。每輪每個頻道最多 MAX_MESSAGES 則，超過的合併成一則摘要。"""

from typing import Any

from stockwatch.rules import AlertPayload

MAX_MESSAGES = 10
SUMMARY_COLOR = 0xF1C40F
DESCRIPTION_LIMIT = 4096


def alert_embed(p: AlertPayload) -> dict[str, Any]:
    return {
        "title": p.title,
        "color": p.color,
        "fields": [{"name": k, "value": v, "inline": True} for k, v in p.fields.items()],
    }


def summary_embed(payloads: list[AlertPayload]) -> dict[str, Any]:
    lines: list[str] = []
    size = 0
    for i, p in enumerate(payloads):
        line = f"{p.title}　{p.fields.get('成交量倍數', 'n/a')}　（{p.rule_id}）"
        if size + len(line) + 1 > DESCRIPTION_LIMIT - 40:
            lines.append(f"…另有 {len(payloads) - i} 則")
            break
        lines.append(line)
        size += len(line) + 1
    return {
        "title": f"另有 {len(payloads)} 則警報（合併顯示）",
        "color": SUMMARY_COLOR,
        "description": "\n".join(lines),
    }


def plan_messages(
    payloads: list[AlertPayload], max_messages: int = MAX_MESSAGES
) -> list[tuple[dict[str, Any], list[AlertPayload]]]:
    """回傳 (webhook payload, 這則訊息涵蓋的警報)。總則數不超過 max_messages。"""
    if len(payloads) <= max_messages:
        return [({"embeds": [alert_embed(p)]}, [p]) for p in payloads]
    head = payloads[: max_messages - 1]
    rest = payloads[max_messages - 1 :]
    messages = [({"embeds": [alert_embed(p)]}, [p]) for p in head]
    messages.append(({"embeds": [summary_embed(rest)]}, rest))
    return messages
