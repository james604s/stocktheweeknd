"""日報 job：cron 0 22 * * * UTC（台灣 06:00），自行判斷前一日是否交易日。

流程見 SPEC.md 第 7 節。最外層 try/except：異常推 #ops 後 re-raise。階段 2 實作。
"""


def main() -> None:
    raise NotImplementedError("階段 2 實作")


if __name__ == "__main__":
    main()
