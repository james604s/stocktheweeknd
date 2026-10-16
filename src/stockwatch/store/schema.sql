-- stockwatch schema（SPEC.md 第 5 節）
-- 只用可攜 SQL：日期與時間戳以 ISO 8601 文字存，時間一律 UTC。

CREATE TABLE IF NOT EXISTS instruments (
    ticker        TEXT PRIMARY KEY,
    name          TEXT,
    market        TEXT NOT NULL,
    in_watchlist  INTEGER NOT NULL DEFAULT 1,
    added_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_bars (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL NOT NULL,
    high    REAL NOT NULL,
    low     REAL NOT NULL,
    close   REAL NOT NULL,
    volume  INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS quotes (
    ticker      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    price       REAL NOT NULL,
    prev_close  REAL NOT NULL,
    day_volume  INTEGER NOT NULL,
    PRIMARY KEY (ticker, ts)
);

CREATE TABLE IF NOT EXISTS indicators (
    ticker       TEXT NOT NULL,
    date         TEXT NOT NULL,
    rsi14        REAL,
    ma20         REAL,
    ma50         REAL,
    ma200        REAL,
    macd         REAL,
    macd_signal  REAL,
    vol_avg20    REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS news (
    id            TEXT PRIMARY KEY,
    ticker        TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    headline      TEXT NOT NULL,
    source        TEXT,
    url           TEXT,
    fetched_at    TEXT NOT NULL
);

-- id 由 transactions.csv 每列內容決定性產生（階段 4），讓重複同步不產生重複列。
CREATE TABLE IF NOT EXISTS transactions (
    id        TEXT PRIMARY KEY,
    date      TEXT NOT NULL,
    ticker    TEXT NOT NULL,
    side      TEXT NOT NULL,
    qty       REAL NOT NULL,
    price     REAL NOT NULL,
    currency  TEXT NOT NULL,
    note      TEXT
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    ticker   TEXT NOT NULL,
    rule_id  TEXT NOT NULL,
    date     TEXT NOT NULL,
    ts       TEXT NOT NULL,
    payload  TEXT NOT NULL,
    PRIMARY KEY (ticker, rule_id, date)
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    date            TEXT PRIMARY KEY,
    prompt_version  TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    text            TEXT NOT NULL
);
