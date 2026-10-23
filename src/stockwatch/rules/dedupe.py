"""去重：同 ticker 同規則同一天只推一次。純函數，查 DB 由呼叫端負責。"""

from collections.abc import Iterable

from stockwatch.rules import AlertPayload


def select_new(
    payloads: Iterable[AlertPayload], already_sent: set[tuple[str, str]]
) -> list[AlertPayload]:
    """排除今天已推過的，以及本輪內重複的 (ticker, rule_id)，保留原順序。"""
    seen = set(already_sent)
    fresh: list[AlertPayload] = []
    for p in payloads:
        if p.key in seen:
            continue
        seen.add(p.key)
        fresh.append(p)
    return fresh
