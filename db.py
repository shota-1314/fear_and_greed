import os
import logging
import psycopg2
from psycopg2.extras import Json
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
    query = """
        INSERT INTO weekly_margin_ratios (ticker, date, margin_ratio)
        VALUES (%s, %s, %s)
        ON CONFLICT (ticker, date)
        DO UPDATE SET margin_ratio = EXCLUDED.margin_ratio;
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (ticker, date_str, margin_ratio))
        logger.info(f"Successfully upserted margin ratio for {ticker} on {date_str}")
    except Exception as e:
        logger.error(f"Failed to upsert margin ratio for {ticker}: {e}")
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
            return pd.DataFrame(columns=["date", "margin_ratio"])
        
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
