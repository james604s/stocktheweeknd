import os
from pathlib import Path

from stockwatch.config import Settings, load_settings, load_watchlist, warn_if_world_readable


def test_settings_repr_hides_secrets():
    s = Settings(
        discord_webhooks={"ops": "https://discord.com/api/webhooks/1/TOKEN"},
        healthchecks_daily="https://hc-ping.com/UUID",
    )
    assert "TOKEN" not in repr(s)
    assert "UUID" not in repr(s)


def test_env_permission_warning(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_WEBHOOK_OPS=x\n")
    os.chmod(env, 0o644)
    assert warn_if_world_readable(env) is True
    os.chmod(env, 0o600)
    assert warn_if_world_readable(env) is False


def test_load_settings_reads_webhooks(tmp_path: Path, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("DISCORD_WEBHOOK_", "HEALTHCHECKS_URL_")):
            monkeypatch.delenv(k)
    env = tmp_path / ".env"
    env.write_text("DISCORD_WEBHOOK_DAILY=https://d\nHEALTHCHECKS_URL_DAILY=https://h\n")
    os.chmod(env, 0o600)
    s = load_settings(env)
    assert s.discord_webhooks == {"daily": "https://d"}
    assert s.healthchecks_daily == "https://h"
    for k in ("DISCORD_WEBHOOK_DAILY", "HEALTHCHECKS_URL_DAILY"):
        monkeypatch.delenv(k, raising=False)


def test_load_watchlist_normalizes(tmp_path: Path):
    wl = tmp_path / "w.yaml"
    wl.write_text("instruments:\n  - {ticker: nvda}\n  - {ticker: ' aapl ', market: US}\n")
    assert [(i.ticker, i.market) for i in load_watchlist(wl)] == [("NVDA", "US"), ("AAPL", "US")]
