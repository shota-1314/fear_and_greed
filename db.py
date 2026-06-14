import os
import logging
import psycopg2
from psycopg2.extras import Json, execute_values
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# PostgreSQLの接続情報
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "fear_and_greed")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "password")

def get_connection():
    """PostgreSQLへの接続を取得する"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def upsert_margin_ratio(ticker: str, date_str: str, margin_ratio: float):
    """
    週次信用倍率をPostgreSQLにUpsertする
    """
    upsert_margin_ratios(ticker, [{"date": date_str, "margin_ratio": margin_ratio}])
    logger.info(f"Successfully upserted margin ratio for {ticker} on {date_str}")

def upsert_margin_ratios(ticker: str, margin_ratios: list[dict]):
    """
    複数件の週次信用倍率をPostgreSQLにUpsertする
    """
    if not margin_ratios:
        logger.info(f"No margin ratios to upsert for {ticker}")
        return

    query = """
        INSERT INTO weekly_margin_ratios (ticker, date, margin_ratio)
        VALUES %s
        ON CONFLICT (ticker, date)
        DO UPDATE SET margin_ratio = EXCLUDED.margin_ratio;
    """
    values = [
        (ticker, item["date"], item.get("margin_ratio"))
        for item in margin_ratios
    ]

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, values)
        logger.info(f"Successfully upserted {len(values)} margin ratios for {ticker}")
    except Exception as e:
        logger.error(f"Failed to upsert margin ratios for {ticker}: {e}")
        raise

def get_latest_margin_date(ticker: str):
    """
    指定銘柄の最新信用倍率日付を取得する
    """
    query = """
        SELECT MAX(date)
        FROM weekly_margin_ratios
        WHERE ticker = %s;
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (ticker,))
                result = cur.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Failed to fetch latest margin date for {ticker}: {e}")
        raise

def get_margin_ratios(ticker: str) -> pd.DataFrame:
    """
    PostgreSQLから過去の信用倍率を取得し、DataFrameとして返す
    """
    query = """
        SELECT date, margin_ratio
        FROM weekly_margin_ratios
        WHERE ticker = %s
        ORDER BY date;
    """
    try:
        with get_connection() as conn:
            # pandasのread_sql_queryを使用して直接DataFrameに読み込む
            import warnings
            with warnings.catch_warnings():
                # psycopg2のコネクションを直接渡す際の警告を抑制
                warnings.simplefilter('ignore', UserWarning)
                df = pd.read_sql_query(query, conn, params=(ticker,))
        
        if df.empty:
            return pd.DataFrame(
                {"margin_ratio": pd.Series(dtype="float64")},
                index=pd.DatetimeIndex([], name="date"),
            )
        
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df[["margin_ratio"]]
    except Exception as e:
        logger.error(f"Failed to fetch margin ratios for {ticker}: {e}")
        raise

def upsert_daily_score(date_str: str, ticker: str, raw_fgi: float, filtered_fgi: float, indicators: dict):
    """
    計算された日次スコアをPostgreSQLにUpsertする
    """
    query = """
        INSERT INTO daily_sentiment_scores (date, ticker, raw_fgi, filtered_fgi, indicators, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (date, ticker)
        DO UPDATE SET 
            raw_fgi = EXCLUDED.raw_fgi,
            filtered_fgi = EXCLUDED.filtered_fgi,
            indicators = EXCLUDED.indicators,
            created_at = NOW();
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # dictをJSONB型として保存するためにpsycopg2.extras.Jsonを使用
                cur.execute(query, (date_str, ticker, raw_fgi, filtered_fgi, Json(indicators)))
        logger.info(f"Successfully upserted daily score for {ticker} on {date_str}")
    except Exception as e:
        logger.error(f"Failed to upsert daily score for {ticker}: {e}")
        raise

