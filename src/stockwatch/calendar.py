"""交易日曆與時段判斷，依 instruments.market 查表。

這是全專案唯一允許知道「哪個市場何時開盤」的地方；
其他模組不得寫死 NYSE 或美東時間。v1 只有 US，階段 3.5 加 TW。
介面於階段 2（交易日判斷）與階段 3（盤中時段）實作。
"""

from typing import Literal

Market = Literal["US"]
