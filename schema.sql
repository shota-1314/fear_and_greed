-- 週次信用倍率マスタ
CREATE TABLE IF NOT EXISTS weekly_margin_ratios (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    margin_ratio FLOAT,
    PRIMARY KEY (ticker, date)
);

-- 日次スコアテーブル
CREATE TABLE IF NOT EXISTS daily_sentiment_scores (
    date DATE NOT NULL,
    ticker TEXT NOT NULL,
    raw_fgi FLOAT,
    filtered_fgi FLOAT,
    indicators JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, ticker)
);

-- 検索を高速化するためのインデックス（オプション）
CREATE INDEX IF NOT EXISTS idx_daily_sentiment_scores_ticker ON daily_sentiment_scores(ticker);
