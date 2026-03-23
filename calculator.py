import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCVと信用倍率が結合されたDataFrameから、C1〜C7のRaw Valueとスコア(0-100)を計算する
    """
    df = df.copy()
    
    # 欠損値の前方補完（休場日等）
    df.ffill(inplace=True)
    
    # C1 (短期モメンタム): 当日終値 / 過去25日間の終値平均 - 1
    df['C1_raw'] = df['Close'] / df['Close'].rolling(window=25).mean() - 1
    
    # C2 (ボラティリティ): 過去20日間の終値の前日比（％）の標準偏差
    df['daily_return'] = df['Close'].pct_change()
    df['C2_raw'] = df['daily_return'].rolling(window=20).std()
    
    # C3 (信用需給): 当日信用倍率 / 過去130営業日の信用倍率平均
    if 'margin_ratio' in df.columns:
        df['C3_raw'] = df['margin_ratio'] / df['margin_ratio'].rolling(window=130).mean()
    else:
        df['C3_raw'] = np.nan
        
    # C4 (RSI): 14日相対力指数（RSI）
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['C4_raw'] = 100 - (100 / (1 + rs))
    
    # C5 (ボリュームレシオ): 過去25日間の「株価上昇日の出来高合計」 / 「株価下落日の出来高合計」
    up_vol = (df['Volume'].where(delta > 0, 0)).rolling(window=25).sum()
    down_vol = (df['Volume'].where(delta < 0, 0)).rolling(window=25).sum()
    # calculator.py の修正
    df['C5_raw'] = up_vol / down_vol.replace(0, np.nan)
    
    # C6 (年間価格レンジ): (当日終値 - 過去252日の最安値) / (過去252日の最高値 - 過去252日の最安値)
    low_252 = df['Low'].rolling(window=252).min()
    high_252 = df['High'].rolling(window=252).max()
    df['C6_raw'] = (df['Close'] - low_252) / (high_252 - low_252)
    
    # C7 (長期トレンド): 当日終値 / 過去200日間の終値平均 - 1
    df['C7_raw'] = df['Close'] / df['Close'].rolling(window=200).mean() - 1
    
    # パーセンタイル順位（0〜100）への変換（過去252日間の分布に基づく）
    def rolling_percentile(series, window=252, positive_corr=True):
        def pct_rank(x):
            s = pd.Series(x)
            if s.dropna().empty: return np.nan
            rank = s.rank(pct=True).iloc[-1] * 100
            return rank if positive_corr else 100 - rank
            
        return series.rolling(window=window, min_periods=window//2).apply(pct_rank, raw=False)

    df['C1_score'] = rolling_percentile(df['C1_raw'], positive_corr=True)
    df['C2_score'] = rolling_percentile(df['C2_raw'], positive_corr=False)
    df['C3_score'] = rolling_percentile(df['C3_raw'], positive_corr=False)
    df['C4_score'] = rolling_percentile(df['C4_raw'], positive_corr=True)
    df['C5_score'] = rolling_percentile(df['C5_raw'], positive_corr=True)
    df['C6_score'] = rolling_percentile(df['C6_raw'], positive_corr=True)
    df['C7_score'] = rolling_percentile(df['C7_raw'], positive_corr=True)
    
    # Raw_FGI: C1〜C7のスコアの平均値（欠損値NaNは除外して平均をとる）
    score_cols = ['C1_score', 'C2_score', 'C3_score', 'C4_score', 'C5_score', 'C6_score', 'C7_score']
    df['raw_fgi'] = df[score_cols].mean(axis=1, skipna=True)
    
    # Filtered_FGI: Raw_FGIの「5日単純移動平均」
    df['filtered_fgi'] = df['raw_fgi'].rolling(window=5).mean()
    
    return df
