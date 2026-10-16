"""盤中哨兵 job：cron */5 * * * *，啟動後自行判斷是否在交易時段，否則直接退出。

流程見 SPEC.md 第 8 節。最外層 try/except：異常推 #ops 後 re-raise。階段 3 實作。
"""


def main() -> None:
    raise NotImplementedError("階段 3 實作")


if __name__ == "__main__":
    main()
