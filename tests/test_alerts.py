from stockwatch.report.alerts import alert_embed, plan_messages
from stockwatch.rules import AlertPayload
from stockwatch.rules.dedupe import select_new


def _p(ticker: str, rule_id: str = "pct_move_5") -> AlertPayload:
    return AlertPayload(
        ticker=ticker,
        rule_id=rule_id,
        title=f"{ticker} ▲ +6.2%",
        fields={"現價": "1", "前收": "1", "成交量倍數": "1.0x", "觸發規則": rule_id},
        channels=("alerts",),
        color=0x2ECC71,
    )


def test_select_new_skips_sent_and_in_round_duplicates():
    payloads = [_p("A"), _p("A"), _p("A", "vol_spike_2x"), _p("B")]
    fresh = select_new(payloads, {("B", "pct_move_5")})
    assert [p.key for p in fresh] == [("A", "pct_move_5"), ("A", "vol_spike_2x")]


def test_alert_embed_format():
    e = alert_embed(_p("NVDA"))
    assert e["title"] == "NVDA ▲ +6.2%"
    assert e["color"] == 0x2ECC71
    assert [f["name"] for f in e["fields"]] == ["現價", "前收", "成交量倍數", "觸發規則"]


def test_plan_messages_within_limit():
    msgs = plan_messages([_p(f"T{i}") for i in range(10)])
    assert len(msgs) == 10
    assert all(len(covered) == 1 for _, covered in msgs)


def test_plan_messages_merges_overflow_into_summary():
    payloads = [_p(f"T{i}") for i in range(25)]
    msgs = plan_messages(payloads)
    assert len(msgs) == 10  # 每輪最多 10 則
    summary, covered = msgs[-1]
    assert len(covered) == 16
    assert summary["embeds"][0]["title"] == "另有 16 則警報（合併顯示）"
    # 所有警報都被某則訊息涵蓋，才能全部寫入 alerts_sent
    assert sum(len(c) for _, c in msgs) == 25
