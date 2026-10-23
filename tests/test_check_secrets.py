"""金鑰掃描：規則本身的測試，以及整個 repo 目前追蹤的檔案都必須乾淨。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_secrets  # noqa: E402

# 測試用的假金鑰一律在執行時組字串，避免檔案本身被掃描器擋下。


def _scan(files: dict[str, str]) -> list[str]:
    return check_secrets.scan(files, files.get)


def test_detects_real_looking_secrets():
    files = {
        "a.py": 'URL = "https://discord.com/api/webhooks/1234567890/' + "a" * 68 + '"',
        "b.md": "key: sk-ant-" + "x" * 40,
        "c.txt": "https://hc-ping.com/" + "-".join(["0a1b2c3d", "1111", "2222", "3333", "4" * 12]),
        "d.sh": "export ANTHROPIC_API_KEY=abc123\nDISCORD_WEBHOOK_OPS='https://x'\n",
    }
    problems = _scan(files)
    assert any(p.startswith("a.py:1") for p in problems)
    assert any(p.startswith("b.md:1") for p in problems)
    assert any(p.startswith("c.txt:1") for p in problems)
    assert any(p.startswith("d.sh:1") for p in problems)
    assert any(p.startswith("d.sh:2") for p in problems)


def test_allows_empty_env_example_and_test_placeholders():
    files = {
        ".env.example": "FINNHUB_KEY=\nANTHROPIC_API_KEY=\n# STOCKWATCH_DB=\n",
        "t.py": 'URL = "https://discord.com/api/webhooks/123/SECRET_TOKEN"',
    }
    assert _scan(files) == []


def test_forbidden_paths():
    for path in (".env", "config/.env", ".env.prod", "data/stock.db", "logs/daily.log", "x.sqlite"):
        assert _scan({path: ""}) == [f"{path}: 這個檔案不該進 git"], path
    assert _scan({".env.example": ""}) == []


def test_repository_has_no_secrets():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_secrets.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
