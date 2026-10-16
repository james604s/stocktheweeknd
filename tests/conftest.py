from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def no_sleep():
    """注入給 retry 的 sleep，記錄延遲秒數但不真的等待。"""
    calls: list[float] = []
    return calls.append, calls
