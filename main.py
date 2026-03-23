import os
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

from fetcher import fetch_ohlcv, scrape_margin_ratios
from db import get_latest_margin_date, upsert_margin_ratios, get_margin_ratios, upsert_daily_score
from calculator import calculate_indicators

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_ticker(ticker: str):
    logger.info(f"--- Starting processing for {ticker} ---")
    
    try:
        # 1. & 2. 株探データの差分更新ロジック
        try:
            # DBに保存されている最新の日付を取得
            latest_db_date = get_latest_margin_date(ticker)
            if latest_db_date:
                logger.info(f"Latest margin date in DB for {ticker}: {latest_db_date}")
            else:
                logger.info(f"No previous margin data found for {ticker}. Will run initial bulk insert.")

            # 株探から過去約30週分をスクレイピング
            scraped_ratios = scrape_margin_ratios(ticker)

            # DBの最新日付より「新しい」データのみを抽出
            new_ratios = []
            for item in scraped_ratios:
                # DBが空(初回) または スクレイピングした日付がDBの最新日付より未来の場合
                if latest_db_date is None or item["date"] > latest_db_date:
                    new_ratios.append(item)

            # 未登録のデータがあればDBへ一括保存
            if new_ratios:
                logger.info(f"Found {len(new_ratios)} new margin ratio records for {ticker}. Upserting...")
                upsert_margin_ratios(ticker, new_ratios)
            else:
                logger.info(f"No new margin ratio data found for {ticker}. DB is up to date.")

        except Exception as e:
            logger.warning(f"Failed to scrape/upsert margin ratio for {ticker}. Continuing with historical data. Error: {e}")
        
        # 3. DBから過去の信用倍率を取得 (ここは既存のままでOK)
        margin_df = get_margin_ratios(ticker)
        
        # 4. yfinanceから過去500営業日分のOHLCVを取得
        ohlcv_df = fetch_ohlcv(ticker, days=500)
        if ohlcv_df.empty:
            logger.error(f"No OHLCV data for {ticker}. Skipping.")
            return
            
        # インデックスを日付のみ（時刻なし）に揃える
        ohlcv_df.index = pd.to_datetime(ohlcv_df.index).normalize()
        if not margin_df.empty:
            margin_df.index = pd.to_datetime(margin_df.index).normalize()
            
        # 5. 信用倍率を日次にリサンプル（ffill）してOHLCVに結合
        if not margin_df.empty:
            # yfinanceの期間に合わせてリサンプル
            date_range = pd.date_range(start=ohlcv_df.index.min(), end=ohlcv_df.index.max(), freq='D')
            margin_daily = margin_df.reindex(date_range).ffill()
            
            # OHLCVと結合
            combined_df = ohlcv_df.join(margin_daily, how='left')
            # 結合後に再度ffill（過去の信用倍率を最新日まで引き継ぐ）
            combined_df['margin_ratio'] = combined_df['margin_ratio'].ffill()
        else:
            logger.warning(f"No margin ratio data available for {ticker}. C3 will be NaN.")
            combined_df = ohlcv_df.copy()
            combined_df['margin_ratio'] = pd.NA
            
        # 6. C1〜C7の計算、パーセンタイル変換、FGI算出
        result_df = calculate_indicators(combined_df)
        
        # 最新日（1日分）を抽出
        latest_date = result_df.index[-1]
        latest_data = result_df.loc[latest_date]
        
        # 欠損値(NaN)のチェックと処理
        if pd.isna(latest_data['raw_fgi']):
            logger.error(f"Calculated raw_fgi is NaN for {ticker} on {latest_date.date()}. Not saving to DB.")
            return
            
        # 7. DBに日次スコアをUpsert
        indicators_json = {
            "C1": {"raw": float(latest_data.get('C1_raw', 0)), "score": float(latest_data.get('C1_score', 0))},
            "C2": {"raw": float(latest_data.get('C2_raw', 0)), "score": float(latest_data.get('C2_score', 0))},
            "C3": {"raw": float(latest_data.get('C3_raw', 0)), "score": float(latest_data.get('C3_score', 0))},
            "C4": {"raw": float(latest_data.get('C4_raw', 0)), "score": float(latest_data.get('C4_score', 0))},
            "C5": {"raw": float(latest_data.get('C5_raw', 0)), "score": float(latest_data.get('C5_score', 0))},
            "C6": {"raw": float(latest_data.get('C6_raw', 0)), "score": float(latest_data.get('C6_score', 0))},
            "C7": {"raw": float(latest_data.get('C7_raw', 0)), "score": float(latest_data.get('C7_score', 0))}
        }
        
        # NaNをNone(null)に変換するヘルパー関数
        def clean_nan(val):
            return None if pd.isna(val) else val
            
        for key in indicators_json:
            indicators_json[key]["raw"] = clean_nan(indicators_json[key]["raw"])
            indicators_json[key]["score"] = clean_nan(indicators_json[key]["score"])
            
        upsert_daily_score(
            date_str=latest_date.strftime("%Y-%m-%d"),
            ticker=ticker,
            raw_fgi=clean_nan(latest_data['raw_fgi']),
            filtered_fgi=clean_nan(latest_data['filtered_fgi']),
            indicators=indicators_json
        )
        
        logger.info(f"--- Successfully completed processing for {ticker} ---")
        
    except Exception as e:
        logger.error(f"Error processing {ticker}: {e}", exc_info=True)

if __name__ == "__main__":
    load_dotenv()
    
    # 対象銘柄リスト（環境変数から取得、またはデフォルト値）
    # 例: "3697.T,7203.T,9984.T"
    tickers_env = os.getenv("TARGET_TICKERS", "3697.T")
    tickers = [t.strip() for t in tickers_env.split(",") if t.strip()]
    
    logger.info(f"Starting batch job for {len(tickers)} tickers: {tickers}")
    
    for ticker in tickers:
        process_ticker(ticker)
        
    logger.info("Batch job finished.")
