import pandas as pd
import ta
import logging

logger = logging.getLogger(__name__)

def compute_rsi(df, period=14):
    try:
        return ta.momentum.RSIIndicator(close=df["close"], window=period).rsi()
    except Exception as e:
        logger.error(f"RSI error: {e}")
        return None

def compute_macd(df, fast=12, slow=26, signal=9):
    try:
        m = ta.trend.MACD(close=df["close"], window_fast=fast, window_slow=slow, window_sign=signal)
        r = pd.DataFrame(index=df.index)
        r["macd_line"] = m.macd()
        r["macd_histogram"] = m.macd_diff()
        r["macd_signal"] = m.macd_signal()
        return r
    except Exception as e:
        logger.error(f"MACD error: {e}")
        return None

def compute_bollinger(df, period=20, std_dev=2.0):
    try:
        b = ta.volatility.BollingerBands(close=df["close"], window=period, window_dev=std_dev)
        r = pd.DataFrame(index=df.index)
        r["bb_lower"] = b.bollinger_lband()
        r["bb_mid"] = b.bollinger_mavg()
        r["bb_upper"] = b.bollinger_hband()
        r["bb_percent_b"] = b.bollinger_pband()
        r["bb_bandwidth"] = b.bollinger_wband()
        return r
    except Exception as e:
        logger.error(f"BB error: {e}")
        return None

def detect_squeeze(bb_data, lookback=100, percentile=20):
    try:
        bw = bb_data["bb_bandwidth"].dropna()
        if len(bw) < lookback:
            lookback = len(bw)
        if lookback < 20:
            return False
        threshold = bw.iloc[-lookback:].quantile(percentile / 100.0)
        return bw.iloc[-1] <= threshold
    except:
        return False

def get_latest_indicators(df, config):
    ic = config.get("indicators", {})
    rsi_s = compute_rsi(df, period=ic.get("rsi", {}).get("period", 14))
    if rsi_s is None:
        return None
    mc = ic.get("macd", {})
    macd_df = compute_macd(df, fast=mc.get("fast", 12), slow=mc.get("slow", 26), signal=mc.get("signal", 9))
    if macd_df is None:
        return None
    bc = ic.get("bollinger", {})
    bb_df = compute_bollinger(df, period=bc.get("period", 20), std_dev=bc.get("std_dev", 2.0))
    if bb_df is None:
        return None
    sq = detect_squeeze(bb_df, lookback=bc.get("squeeze_lookback", 100), percentile=bc.get("squeeze_percentile", 20))
    return {
        "rsi": float(rsi_s.iloc[-1]),
        "rsi_series": rsi_s,
        "macd": {"line": float(macd_df["macd_line"].iloc[-1]), "histogram": float(macd_df["macd_histogram"].iloc[-1]), "signal": float(macd_df["macd_signal"].iloc[-1]), "histogram_prev": float(macd_df["macd_histogram"].iloc[-2]), "line_prev": float(macd_df["macd_line"].iloc[-2]), "signal_prev": float(macd_df["macd_signal"].iloc[-2])},
        "macd_df": macd_df,
        "bb": {"percent_b": float(bb_df["bb_percent_b"].iloc[-1]), "bandwidth": float(bb_df["bb_bandwidth"].iloc[-1]), "upper": float(bb_df["bb_upper"].iloc[-1]), "lower": float(bb_df["bb_lower"].iloc[-1]), "mid": float(bb_df["bb_mid"].iloc[-1]), "squeeze": sq},
        "bb_df": bb_df,
        "close_series": df["close"],
    }
