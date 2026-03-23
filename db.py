import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def upsert_margin_ratio(ticker: str, date_str: str, margin_ratio: float):
    """
    週次信用倍率をSupabaseにUpsertする
    """
    try:
        data = {
            "ticker": ticker,
            "date": date_str,
            "margin_ratio": margin_ratio
        }
        response = supabase.table("weekly_margin_ratios").upsert(data).execute()
        logger.info(f"Successfully upserted margin ratio for {ticker} on {date_str}")
        return response
    except Exception as e:
        logger.error(f"Failed to upsert margin ratio for {ticker}: {e}")
        raise

def get_margin_ratios(ticker: str) -> pd.DataFrame:
    """
    Supabaseから過去の信用倍率を取得し、DataFrameとして返す
    """
    try:
        response = supabase.table("weekly_margin_ratios").select("*").eq("ticker", ticker).order("date").execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["date", "margin_ratio"])
        
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df[["margin_ratio"]]
    except Exception as e:
        logger.error(f"Failed to fetch margin ratios for {ticker}: {e}")
        raise

def upsert_daily_score(date_str: str, ticker: str, raw_fgi: float, filtered_fgi: float, indicators: dict):
    """
    計算された日次スコアをSupabaseにUpsertする
    """
    try:
        data = {
            "date": date_str,
            "ticker": ticker,
            "raw_fgi": raw_fgi,
            "filtered_fgi": filtered_fgi,
            "indicators": indicators
        }
        response = supabase.table("daily_sentiment_scores").upsert(data).execute()
        logger.info(f"Successfully upserted daily score for {ticker} on {date_str}")
        return response
    except Exception as e:
        logger.error(f"Failed to upsert daily score for {ticker}: {e}")
        raise
