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

def scrape_margin_ratio(ticker: str) -> tuple[str, float]:
    """
    株探から最新の信用倍率をスクレイピングする
    ※複雑なページネーション処理はモック化し、最新の1件を取得する想定
    戻り値: (日付文字列(YYYY-MM-DD), 信用倍率)
    """
    # 銘柄コードから「.T」などを除去（例: 3697.T -> 3697）
    base_ticker = ticker.split('.')[0]
    url = f"https://s.kabutan.jp/stocks/{base_ticker}/historical_prices/daily/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        logger.info(f"Scraping margin ratio for {ticker} from {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # --- モック実装 ---
        # 実際のDOM構造に合わせてパースする必要がありますが、ここではモック値を返します。
        # 本番環境では、soup.find() 等を用いて正しいテーブルのセルから日付と倍率を抽出してください。
        # 例:
        # table = soup.find('table', class_='historical_prices')
        # row = table.find_all('tr')[1] # 最新行
        # date_str = row.find_all('td')[0].text
        # margin_ratio = float(row.find_all('td')[X].text)
        
        # モックとして、本日日付とダミーの倍率を返す
        mock_date = datetime.now().strftime("%Y-%m-%d")
        mock_ratio = 1.5 # ダミー値
        
        logger.info(f"Scraped margin ratio: {mock_ratio} on {mock_date} (MOCK)")
        return mock_date, mock_ratio
        
    except Exception as e:
        logger.error(f"Failed to scrape margin ratio for {ticker}: {e}")
        raise
