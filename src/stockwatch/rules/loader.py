"""從 rules.yaml 建立規則。設定錯誤時立即拋錯，不默默略過。"""

from pathlib import Path
from typing import Any

import yaml

from stockwatch.config import CHANNELS
from stockwatch.rules import Rule
from stockwatch.rules.builtin import pct_change_vs_prev_close, volume_vs_avg20


def _channels(rule_id: str, raw: Any) -> tuple[str, ...]:
    channels = tuple(raw or ("alerts",))
    unknown = [c for c in channels if c not in CHANNELS]
    if unknown:
        raise ValueError(f"{rule_id}: 未知頻道 {unknown}，可用：{', '.join(CHANNELS)}")
    return channels


def build_rule(spec: dict[str, Any]) -> Rule:
    rule_id = str(spec.get("id") or "")
    if not rule_id:
        raise ValueError(f"規則缺少 id：{spec}")
    rule_type = spec.get("type")
    channels = _channels(rule_id, spec.get("channels"))
    try:
        if rule_type == "pct_change_vs_prev_close":
            return pct_change_vs_prev_close(
                rule_id=rule_id, threshold=float(spec["threshold"]), channels=channels
            )
        if rule_type == "volume_vs_avg20":
            return volume_vs_avg20(
                rule_id=rule_id,
                multiplier=float(spec["multiplier"]),
                channels=channels,
                basis=str(spec.get("basis", "full_day")),
            )
    except KeyError as exc:
        raise ValueError(f"{rule_id}: 缺少參數 {exc.args[0]}") from None
    raise ValueError(f"{rule_id}: 未知規則類型 {rule_type!r}")


def load_rules(path: Path) -> list[Rule]:
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    specs = data.get("rules") or []
    ids = [str(s.get("id")) for s in specs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"規則 id 重複：{sorted(dupes)}")
    return [build_rule(s) for s in specs]
