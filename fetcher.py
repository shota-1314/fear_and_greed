import logging
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def fetch_ohlcv(ticker: str, days: int = 500) -> pd.DataFrame:
    """
    yfinanceを用いて過去N日分のOHLCVデータを取得する
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.5)) # 営業日換算のため余裕を持たせる
    
    try:
        logger.info(f"Fetching OHLCV data for {ticker} from {start_date.date()} to {end_date.date()}")
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            logger.warning(f"No data found for {ticker}")
            return pd.DataFrame()
            
        # yfinanceのMultiIndexカラムをフラット化（単一銘柄の場合）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.tail(days) # 指定された日数分に絞る
        return df
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV for {ticker}: {e}")
        raise

def scrape_margin_ratios(ticker: str) -> list[dict]:
    """
    株探の「信用残系列」ページから過去約30週分の信用倍率をスクレイピングする
    戻り値: [{"date": "YYYY-MM-DD", "margin_ratio": 1.5 or None}, ...]
    """
    base_ticker = ticker.split('.')[0]
    url = f"https://kabutan.jp/stock/kabuka?code={base_ticker}&ashi=shin"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        logger.info(f"Scraping multiple margin ratios for {ticker} from {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # テーブルの全行を取得
        rows = soup.select('#stock_kabuka_table table.stock_kabuka_dwm tbody tr')
        if not rows:
            raise ValueError("株探のページから対象のテーブル行が見つかりませんでした。")
            
        results = []
        
        # 全行をループ処理してリストに格納
        for row in rows:
            time_tag = row.select_one('th time')
            if not time_tag:
                continue
                
            raw_date = time_tag.text.strip()
            date_str = datetime.strptime(raw_date, "%y/%m/%d").strftime("%Y-%m-%d")
            
            tds = row.find_all('td')
            if len(tds) < 8:
                continue
                
            ratio_str = tds[7].text.strip()
            
            if ratio_str == '-':
                margin_ratio = None
            else:
                margin_ratio = float(ratio_str.replace(',', ''))
                
            results.append({
                "date": date_str,
                "margin_ratio": margin_ratio
            })
            
        logger.info(f"Successfully scraped {len(results)} weeks of data.")
        return results
        
    except Exception as e:
        logger.error(f"Failed to scrape margin ratios for {ticker}: {e}")
        raise
