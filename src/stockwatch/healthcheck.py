"""healthchecks.io ping（dead man's switch）。失敗只記 log，不影響 job 結果。

ping URL 內含金鑰，錯誤訊息不得帶 URL。
"""

import logging
import time
from collections.abc import Callable

import httpx

from stockwatch.redact import quiet_http_loggers, redact
from stockwatch.retry import retry

log = logging.getLogger(__name__)
quiet_http_loggers()


def ping(
    url: str,
    *,
    fail: bool = False,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    target = url.rstrip("/") + ("/fail" if fail else "")

    def get() -> None:
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                client.get(target).raise_for_status()
        except httpx.HTTPError as exc:
            detail = redact(str(exc), target, url)
            raise RuntimeError(f"{type(exc).__name__}: {detail}") from None

    try:
        retry(get, attempts=3, sleep=sleep, what="healthchecks ping")
    except Exception as exc:
        log.error("healthchecks ping 失敗：%s", exc)
        return False
    return True
