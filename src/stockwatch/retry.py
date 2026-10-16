"""外部呼叫共用的指數退避 retry。

所有對 yfinance、Finnhub、Claude、Discord、healthchecks 的呼叫都必須經過這裡。
"""

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


def retry[T](
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    what: str = "",
) -> T:
    """執行 fn，失敗時以 base_delay * 2**n 秒退避重試，最多 attempts 次。"""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if i == attempts - 1:
                break
            delay = base_delay * 2**i
            log.warning(
                "%s 失敗（第 %d/%d 次）：%s；%.1f 秒後重試",
                what or "呼叫",
                i + 1,
                attempts,
                exc,
                delay,
            )
            sleep(delay)
    assert last is not None
    raise last
