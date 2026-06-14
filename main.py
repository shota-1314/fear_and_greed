import os
import logging
import argparse
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests
import jpholiday # 祝日判定用に追加

# JST（日本標準時）の定義
JST = timezone(timedelta(hours=9), 'JST')

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
            # DBに保存されている【すべての日付】を取得し、検索の速いSet（集合）にしておく
            margin_df = get_margin_ratios(ticker)
            existing_dates = set(margin_df.index.strftime("%Y-%m-%d").tolist()) if not margin_df.empty else set()

            if existing_dates:
                logger.info(f"Found {len(existing_dates)} existing margin ratio records in DB for {ticker}.")
            else:
                logger.info(f"No previous margin data found for {ticker}. Will run initial bulk insert.")

            # 株探から複数ページ分（約60週分）をスクレイピング
            scraped_ratios = scrape_margin_ratios(ticker)

            # DBに存在しない（未登録の）データのみを差分抽出
            new_ratios = []
            for item in scraped_ratios:
                if item["date"] not in existing_dates:
                    new_ratios.append(item)

            # 未登録のデータがあればDBへ一括保存
            if new_ratios:
                logger.info(f"Found {len(new_ratios)} new margin ratio records for {ticker}. Upserting...")
                upsert_margin_ratios(ticker, new_ratios)
                
                # 過去データが追加されたので、その後のC3計算のためにDBから最新状態を再取得する
                margin_df = get_margin_ratios(ticker)
            else:
                logger.info(f"No new margin ratio data found for {ticker}. DB is up to date.")

        except Exception as e:
            logger.warning(f"Failed to scrape/upsert margin ratio for {ticker}. Continuing with historical data. Error: {e}")
        
        # 4. yfinanceから過去500営業日分のOHLCVを取得
        ohlcv_df = fetch_ohlcv(ticker, days=500)
        if ohlcv_df.empty:
            logger.error(f"No OHLCV data for {ticker}. Skipping.")
            return
            
        # インデックスを日付のみ（時刻なし）に揃える
        # main.py の修正（2箇所）
        ohlcv_df.index = pd.to_datetime(ohlcv_df.index).normalize().tz_localize(None)
        if not margin_df.empty:
            margin_df.index = pd.to_datetime(margin_df.index).normalize().tz_localize(None)
            
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

def trigger_gas_update(gas_url: str):
    """
    GASへ結果シート更新を依頼する。
    Apps ScriptはHTTP 200でも本文にErrorを返すことがあるため、本文もログに残す。
    """
    response = requests.post(
        gas_url,
        json={"action": "update_results"},
        timeout=60,
    )
    body = response.text.strip()
    logger.info(f"GAS update response: status={response.status_code}, body={body[:500]}")
    response.raise_for_status()

    if body and body.lower().startswith("error"):
        raise RuntimeError(f"GAS returned an error response: {body}")

# --- main.py の末尾 ---

if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser(description="Fear & Greed Index daily batch")
    parser.add_argument(
        "--test",
        action="store_true",
        help="テスト実行。取得した銘柄リストの先頭5件だけ処理し、GAS更新とLINE通知をスキップします。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="処理する銘柄数の上限。例: --limit 5",
    )
    args = parser.parse_args()
    
    # ==========================================
    # 1. 営業日判定（本番環境のみスキップする）
    # ==========================================
    # Render等の本番環境では環境変数 ENV=production を設定する想定
    is_production = os.getenv("ENV") == "production"
    
    if is_production:
        now_jst = datetime.now(JST)
        # 土日（5:土, 6:日）または 日本の祝日か判定
        if now_jst.weekday() >= 5 or jpholiday.is_holiday(now_jst):
            logger.info(f"Today ({now_jst.strftime('%Y-%m-%d')}) is a weekend or public holiday in Japan. Skipping execution.")
            exit(0) # 処理を終了する
        else:
            logger.info("Today is a business day. Proceeding with execution.")
    else:
        logger.info("Running in Local environment. Skipping holiday check.")

    # ==========================================
    # 2. GAS連携 ＆ FGIバッチ処理
    # ==========================================
    GAS_URL = os.getenv("GAS_WEB_APP_URL")
    if not GAS_URL:
        logger.error("GAS_WEB_APP_URL is not set.")
        exit(1)
    
    logger.info("Fetching target tickers from Google Spreadsheet...")
    try:
        response = requests.get(f"{GAS_URL}?action=get_tickers")
        response.raise_for_status()
        tickers = response.json()
        logger.info(f"Successfully fetched {len(tickers)} tickers.")
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        tickers = []

    original_ticker_count = len(tickers)
    if args.test:
        tickers = tickers[:5]
        logger.info(
            f"Test mode enabled. Processing first {len(tickers)} of {original_ticker_count} tickers. "
            "GAS update and LINE notification will be sent with test messaging."
        )
    elif args.limit is not None:
        if args.limit <= 0:
            logger.error("--limit must be greater than 0.")
            exit(1)
        tickers = tickers[:args.limit]
        logger.info(f"Limit enabled. Processing first {len(tickers)} of {original_ticker_count} tickers.")
    
    if tickers:
        logger.info("Starting batch processing...")
        for ticker in tickers:
            process_ticker(str(ticker).strip())
            
            # 【追加】Yahoo!ファイナンスのアクセス制限（Rate Limit）を回避するため、
            # 1銘柄の処理が終わるごとに3秒間待機する
            logger.info(f"Sleeping for 2 seconds to avoid rate limits...")
            time.sleep(2)
            
        logger.info("Batch processing completed.")
        
        logger.info("Triggering GAS to update the Results sheet...")
        try:
            trigger_gas_update(GAS_URL)
            logger.info("GAS triggered successfully.")
        except Exception as e:
            logger.error(f"Failed to trigger GAS: {e}")

    # ==========================================
    # 3. LINEへ完了通知をブロードキャスト送信
    # ==========================================
    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    spreadsheet_url = os.getenv("SPREADSHEET_URL", "（URL未設定）")

    if line_token:
        logger.info("Sending broadcast message to LINE...")
        
        # LINEに送信するメッセージの内容
        notification_title = "【テスト実行】Fear & Greed Index 算出完了" if args.test else "本日のFear & Greed Index 算出完了"
        notification_detail = (
            f"テストモードで先頭{len(tickers)}件のみ処理しました。"
            if args.test
            else f"対象銘柄（{len(tickers)}件）のデータ更新とスプレッドシートへの反映が完了しました。"
        )
        message_text = (
            f"📊 {notification_title}\n\n"
            f"{notification_detail}\n\n"
            f"▼最新の結果シートはこちら\n{spreadsheet_url}"
        )
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }
        payload = {
            "messages": [
                {
                    "type": "text",
                    "text": message_text
                }
            ]
        }
        
        try:
            # Broadcast API（Botを友だち追加している人・参加しているグループ全員に送信）
            res = requests.post("https://api.line.me/v2/bot/message/broadcast", headers=headers, json=payload)
            res.raise_for_status()
            logger.info("Successfully sent LINE broadcast message.")
        except Exception as e:
            logger.error(f"Failed to send LINE message: {e}")
    else:
        logger.info("LINE_CHANNEL_ACCESS_TOKEN is not set. Skipping LINE notification.")

    logger.info("All pipeline finished.")