from pathlib import Path

import pytest

from stockwatch.config import CONFIG_DIR
from stockwatch.rules.loader import build_rule, load_rules


def test_load_repo_rules_yaml():
    rules = load_rules(CONFIG_DIR / "rules.yaml")
    assert len(rules) == 2


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"type": "pct_change_vs_prev_close", "threshold": 0.05}, "缺少 id"),
        ({"id": "a", "type": "nope"}, "未知規則類型"),
        ({"id": "a", "type": "pct_change_vs_prev_close"}, "缺少參數 threshold"),
        ({"id": "a", "type": "volume_vs_avg20", "multiplier": 2, "basis": "x"}, "basis"),
        (
            {"id": "a", "type": "pct_change_vs_prev_close", "threshold": 0.1, "channels": ["x"]},
            "未知頻道",
        ),
    ],
)
def test_invalid_specs(spec, message):
    with pytest.raises(ValueError, match=message):
        build_rule(spec)


def test_duplicate_ids(tmp_path: Path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n"
        "  - {id: a, type: pct_change_vs_prev_close, threshold: 0.05}\n"
        "  - {id: a, type: volume_vs_avg20, multiplier: 2}\n"
    )
    with pytest.raises(ValueError, match="重複"):
        load_rules(path)
