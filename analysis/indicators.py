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

def compute_ema_cross(df, fast=50, slow=200):
    try:
        ema_fast = ta.trend.EMAIndicator(close=df["close"], window=fast).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(close=df["close"], window=slow).ema_indicator()
        r = pd.DataFrame(index=df.index)
        r["ema_fast"] = ema_fast
        r["ema_slow"] = ema_slow
        return r
    except Exception as e:
        logger.error(f"EMA cross error: {e}")
        return None

def compute_adx(df, period=14):
    try:
        adx_ind = ta.trend.ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        return adx_ind.adx()
    except Exception as e:
        logger.error(f"ADX error: {e}")
        return None

def compute_obv(df):
    try:
        obv = ta.volume.OnBalanceVolumeIndicator(
            close=df["close"], volume=df["volume"]
        )
        return obv.on_balance_volume()
    except Exception as e:
        logger.error(f"OBV error: {e}")
        return None

def compute_stoch_rsi(df, period=14, smooth_k=3, smooth_d=3):
    try:
        s = ta.momentum.StochRSIIndicator(
            close=df["close"], window=period, smooth1=smooth_k, smooth2=smooth_d
        )
        r = pd.DataFrame(index=df.index)
        r["stoch_rsi_k"] = s.stochrsi_k()
        r["stoch_rsi_d"] = s.stochrsi_d()
        return r
    except Exception as e:
        logger.error(f"StochRSI error: {e}")
        return None

def get_latest_indicators(df, config):
    ic = config.get("indicators", {})

    # --- Existing indicators ---
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

    # --- New indicators ---
    ec = ic.get("ema", {})
    ema_df = compute_ema_cross(df, fast=ec.get("fast", 50), slow=ec.get("slow", 200))

    adx_s = compute_adx(df, period=ic.get("adx", {}).get("period", 14))

    obv_s = None
    if "volume" in df.columns and df["volume"].notna().any():
        obv_s = compute_obv(df)

    src = ic.get("stoch_rsi", {})
    stoch_df = compute_stoch_rsi(
        df,
        period=src.get("period", 14),
        smooth_k=src.get("smooth_k", 3),
        smooth_d=src.get("smooth_d", 3),
    )

    result = {
        "rsi": float(rsi_s.iloc[-1]),
        "rsi_series": rsi_s,
        "macd": {
            "line": float(macd_df["macd_line"].iloc[-1]),
            "histogram": float(macd_df["macd_histogram"].iloc[-1]),
            "signal": float(macd_df["macd_signal"].iloc[-1]),
            "histogram_prev": float(macd_df["macd_histogram"].iloc[-2]),
            "line_prev": float(macd_df["macd_line"].iloc[-2]),
            "signal_prev": float(macd_df["macd_signal"].iloc[-2]),
        },
        "macd_df": macd_df,
        "bb": {
            "percent_b": float(bb_df["bb_percent_b"].iloc[-1]),
            "bandwidth": float(bb_df["bb_bandwidth"].iloc[-1]),
            "upper": float(bb_df["bb_upper"].iloc[-1]),
            "lower": float(bb_df["bb_lower"].iloc[-1]),
            "mid": float(bb_df["bb_mid"].iloc[-1]),
            "squeeze": sq,
        },
        "bb_df": bb_df,
        "close_series": df["close"],
    }

    # EMA cross
    if ema_df is not None:
        ema_fast_val = float(ema_df["ema_fast"].iloc[-1])
        ema_slow_val = float(ema_df["ema_slow"].iloc[-1])
        ema_fast_prev = float(ema_df["ema_fast"].iloc[-2])
        ema_slow_prev = float(ema_df["ema_slow"].iloc[-2])
        price = float(df["close"].iloc[-1])
        result["ema"] = {
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
            "golden_cross": ema_fast_prev < ema_slow_prev and ema_fast_val > ema_slow_val,
            "death_cross": ema_fast_prev > ema_slow_prev and ema_fast_val < ema_slow_val,
            "above_slow": price > ema_slow_val,
            "fast_above_slow": ema_fast_val > ema_slow_val,
            "price": price,
        }

    # ADX — trend strength (used as confidence multiplier, not scored)
    if adx_s is not None:
        result["adx"] = float(adx_s.iloc[-1])

    # OBV
    if obv_s is not None:
        obv_now = float(obv_s.iloc[-1])
        obv_prev5 = float(obv_s.iloc[-6:-1].mean())
        price_now = float(df["close"].iloc[-1])
        price_prev5 = float(df["close"].iloc[-6:-1].mean())
        result["obv"] = {
            "value": obv_now,
            "trend_up": obv_now > obv_prev5,
            "price_trend_up": price_now > price_prev5,
            "obv_series": obv_s,
        }

    # Stochastic RSI
    if stoch_df is not None:
        k = float(stoch_df["stoch_rsi_k"].iloc[-1])
        d = float(stoch_df["stoch_rsi_d"].iloc[-1])
        k_prev = float(stoch_df["stoch_rsi_k"].iloc[-2])
        d_prev = float(stoch_df["stoch_rsi_d"].iloc[-2])
        result["stoch_rsi"] = {
            "k": k,
            "d": d,
            "k_prev": k_prev,
            "d_prev": d_prev,
            "k_cross_up": k_prev < d_prev and k > d,
            "k_cross_down": k_prev > d_prev and k < d,
        }

    return result
