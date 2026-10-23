"""日報組裝。

日報由 section 列表組成，每個 section 是獨立函數，回傳 Discord embed field(s)。
新增區塊只需新增一個函數並加進 sections.SECTIONS，不動既有程式。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbedField:
    name: str
    value: str
    inline: bool = False
