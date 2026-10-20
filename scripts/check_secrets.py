#!/usr/bin/env python3
"""掃描 git 追蹤或暫存的檔案，發現金鑰或不該進 git 的檔案就以非零退出。

只用標準函式庫，pre-commit hook 可直接以 python3 執行，不依賴 uv。

用法：
    python3 scripts/check_secrets.py            # 掃描所有追蹤中的檔案
    python3 scripts/check_secrets.py --staged   # 只掃描暫存區（pre-commit 用）
"""

import re
import subprocess
import sys
from collections.abc import Iterable

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "Discord webhook": re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}"),
    "Anthropic API key": re.compile(r"sk-ant-[\w-]{20,}"),
    "healthchecks ping URL": re.compile(
        r"hc-ping\.com/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    ),
    ".env 金鑰賦值": re.compile(
        r"^[ \t]*(?:export[ \t]+)?"
        r"(?:FINNHUB_KEY|ANTHROPIC_API_KEY|DISCORD_WEBHOOK_\w+|HEALTHCHECKS_URL_\w+)"
        r"[ \t]*=[ \t]*['\"]?[^\s'\"#]+",
        re.MULTILINE,
    ),
}

FORBIDDEN_PATHS = re.compile(
    r"(^|/)\.env$|(^|/)\.env\.(?!example$)[^/]+$|^(data|logs|backups)/|\.(db|sqlite3?|pem|key)$"
)


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def _files(staged: bool) -> list[str]:
    if staged:
        out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        out = _git("ls-files", "-z")
    return [p for p in out.decode().split("\0") if p]


def _content(path: str, staged: bool) -> str | None:
    try:
        data = _git("show", f":{path}") if staged else open(path, "rb").read()
    except (subprocess.CalledProcessError, OSError):
        return None
    if b"\0" in data[:8000]:
        return None  # 二進位檔
    return data.decode("utf-8", errors="replace")


def scan(files: Iterable[str], read) -> list[str]:
    problems: list[str] = []
    for path in files:
        if FORBIDDEN_PATHS.search(path):
            problems.append(f"{path}: 這個檔案不該進 git")
            continue
        text = read(path)
        if text is None:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{path}:{line}: 疑似 {name}")
    return problems


def main(argv: list[str]) -> int:
    staged = "--staged" in argv
    problems = scan(_files(staged), lambda p: _content(p, staged))
    if problems:
        print("❌ 發現疑似金鑰或不該進 git 的檔案：", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("金鑰只放 VPS 的 .env；若是誤判，請調整 scripts/check_secrets.py。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
