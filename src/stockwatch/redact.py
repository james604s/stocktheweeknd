"""從錯誤訊息與 log 中遮蔽金鑰（webhook URL、healthchecks URL 都含金鑰）。"""

import logging


def redact(text: str, *secrets: str) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return text


def quiet_http_loggers() -> None:
    """httpx 在 INFO 等級會記錄每個請求的完整 URL，金鑰會因此進 log。"""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
