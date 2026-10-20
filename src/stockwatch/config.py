"""設定載入：config/watchlist.yaml 與 .env。"""

import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
CHANNELS = ("daily", "alerts", "holdings", "ops")


@dataclass(frozen=True, slots=True)
class Instrument:
    ticker: str
    market: str


def load_watchlist(path: Path) -> list[Instrument]:
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    items = data.get("instruments") or []
    return [
        Instrument(ticker=str(item["ticker"]).strip().upper(), market=str(item.get("market", "US")))
        for item in items
    ]


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path = PROJECT_ROOT / "data" / "stock.db"
    watchlist_path: Path = CONFIG_DIR / "watchlist.yaml"
    # 以下欄位含金鑰，repr=False 避免被 log 或錯誤訊息印出
    discord_webhooks: dict[str, str] = field(default_factory=dict, repr=False)
    healthchecks_daily: str | None = field(default=None, repr=False)
    healthchecks_watch: str | None = field(default=None, repr=False)


def warn_if_world_readable(path: Path) -> bool:
    """.env 應為 600；group 或 others 可讀時記 warning 並回傳 True。"""
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        log.warning("%s 權限為 %o，請執行 chmod 600 %s", path, stat.S_IMODE(mode), path)
        return True
    return False


def load_settings(env_file: Path | None = PROJECT_ROOT / ".env") -> Settings:
    """從 .env（若存在）與環境變數讀設定。金鑰只存在 VPS 的 .env。"""
    if env_file is not None and env_file.exists():
        warn_if_world_readable(env_file)
        load_dotenv(env_file)
    env = os.environ
    webhooks = {
        channel: url
        for channel in CHANNELS
        if (url := env.get(f"DISCORD_WEBHOOK_{channel.upper()}"))
    }
    return Settings(
        db_path=Path(env.get("STOCKWATCH_DB", PROJECT_ROOT / "data" / "stock.db")),
        discord_webhooks=webhooks,
        healthchecks_daily=env.get("HEALTHCHECKS_URL_DAILY") or None,
        healthchecks_watch=env.get("HEALTHCHECKS_URL_WATCH") or None,
    )
