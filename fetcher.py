import logging
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone # timezone を追加
import time

logger = logging.getLogger(__name__)

# JST（日本標準時: UTC+9）を定数として定義
JST = timezone(timedelta(hours=9), 'JST')

def fetch_ohlcv(ticker: str, days: int = 500) -> pd.DataFrame:
    """
    yfinanceを用いて過去N日分のOHLCVデータを取得する
    """
    # サーバーのローカル時間に依存せず、明示的にJSTで「現在」を取得
    end_date = datetime.now(JST)
    start_date = end_date - timedelta(days=int(days * 1.5))
    
    # yfinanceのタイムゾーンバグを防ぐため、文字列（YYYY-MM-DD）に変換して渡す
    end_str = end_date.strftime('%Y-%m-%d')
    start_str = start_date.strftime('%Y-%m-%d')
    
    yf_ticker = f"{ticker}.T" if not str(ticker).endswith('.T') else str(ticker)
    
    try:
        logger.info(f"Fetching OHLCV data for {yf_ticker} from {start_str} to {end_str} (JST)")
        df = yf.download(yf_ticker, start=start_str, end=end_str, progress=False)
        
        if df.empty:
            logger.warning(f"No data found for {yf_ticker}")
            return pd.DataFrame()
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.tail(days)
        return df
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV for {yf_ticker}: {e}")
        raise

def scrape_margin_ratios(ticker: str, max_pages: int = 2) -> list[dict]:
    """
    株探の「信用残系列」ページから過去の信用倍率を複数ページにわたってスクレイピングする
    デフォルトで2ページ分（約60週分）を取得し、C3計算に必要な50週をカバーする
    """
    base_ticker = ticker.split('.')[0]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    results = []
    
    # page=1 から max_pages(デフォルト2) までループ
    for page in range(1, max_pages + 1):
        url = f"https://kabutan.jp/stock/kabuka?code={base_ticker}&ashi=shin&page={page}"
        
        try:
            logger.info(f"Scraping margin ratios for {ticker} from {url}")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            rows = soup.select('#stock_kabuka_table table.stock_kabuka_dwm tbody tr')
            
            # テーブルに行が存在しない場合（最終ページを超えた場合）は終了
            if not rows:
                logger.info(f"No more rows found on page {page}. Stopping pagination.")
                break
                
            page_results = []
            
            for row in rows:
                time_tag = row.select_one('th time')
                if not time_tag:
                    continue
                    
                raw_date = time_tag.text.strip()
                date_str = datetime.strptime(raw_date, "%y/%m/%d").strftime("%Y-%m-%d")
                
                tds = row.find_all('td')
                if len(tds) < 7:
                    continue
                    
                ratio_str = tds[6].text.strip()
                
                if ratio_str in ['-', '－', '']:
                    margin_ratio = None
                else:
                    margin_ratio = float(ratio_str.replace(',', ''))
                    
                page_results.append({
                    "date": date_str,
                    "margin_ratio": margin_ratio
                })
                
            results.extend(page_results)
            logger.info(f"Scraped {len(page_results)} weeks of data from page {page}.")
            
            # 次のページがある場合は、スクレイピングのマナーとして1秒待機
            if page < max_pages:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to scrape margin ratios for {ticker} on page {page}: {e}")
            # 1ページ目で失敗した場合はそのままエラーとするが、
            # 2ページ目以降の失敗は、それまでに取得できたデータを活かしてリターンする
            if page == 1:
                raise
            else:
                break
                
    logger.info(f"Successfully scraped total {len(results)} weeks of data.")
    return results