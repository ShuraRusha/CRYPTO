"""
Technical indicator scoring.
Maps raw indicator values to scores in [-100, +100] range.
"""
import logging
from analysis.divergence import detect_divergence, get_divergence_bonus, divergence_label

logger = logging.getLogger(__name__)


def _interpolate(value: float, low: float, high: float, score_low: float, score_high: float) -> float:
    """Linear interpolation between two points, clamped."""
    if high == low:
        return (score_low + score_high) / 2
    t = (value - low) / (high - low)
    t = max(0.0, min(1.0, t))
    return score_low + t * (score_high - score_low)


def clamp(value: float, lo: float = -100, hi: float = 100) -> float:
    return max(lo, min(hi, value))


# ----------------------------------------------------------------
# RSI Scoring
# ----------------------------------------------------------------
def score_rsi(rsi_value: float, indicators: dict, config: dict) -> dict:
    """
    Score RSI value + detect divergence.
    Returns: {score, divergence_type, divergence_bonus, divergence_label, total}
    """
    # Base RSI score
    if rsi_value <= 15:
        base = 100.0
    elif rsi_value <= 30:
        base = _interpolate(rsi_value, 15, 30, 100, 50)
    elif rsi_value <= 45:
        base = _interpolate(rsi_value, 30, 45, 50, 0)
    elif rsi_value <= 55:
        base = _interpolate(rsi_value, 45, 55, 0, 0)
    elif rsi_value <= 70:
        base = _interpolate(rsi_value, 55, 70, 0, -50)
    elif rsi_value <= 85:
        base = _interpolate(rsi_value, 70, 85, -50, -100)
    else:
        base = -100.0

    # RSI divergence
    rsi_series = indicators.get("rsi_series")
    close_series = indicators.get("close_series")
    lookback = config.get("indicators", {}).get("rsi", {}).get("divergence_lookback", 30)

    div_type = "none"
    div_bonus = 0
    div_label = ""

    if rsi_series is not None and close_series is not None:
        div_type = detect_divergence(close_series, rsi_series, lookback=lookback)
        div_bonus = get_divergence_bonus(div_type, config)
        div_label = divergence_label(div_type)

    total = clamp(base + div_bonus)

    return {
        "score": round(base, 1),
        "divergence_type": div_type,
        "divergence_bonus": div_bonus,
        "divergence_label": div_label,
        "total": round(total, 1),
    }


# ----------------------------------------------------------------
# MACD Scoring
# ----------------------------------------------------------------
def score_macd(macd_data: dict, indicators: dict, config: dict) -> dict:
    """
    Score MACD based on histogram, line position, and divergence.
    """
    hist = macd_data["histogram"]
    hist_prev = macd_data["histogram_prev"]
    line = macd_data["line"]
    signal = macd_data["signal"]
    line_prev = macd_data["line_prev"]
    signal_prev = macd_data["signal_prev"]

    # Component 1: Histogram direction (40%)
    hist_rising = hist > hist_prev
    if hist > 0 and hist_rising:
        hist_score = 50
    elif hist > 0 and not hist_rising:
        hist_score = 15
    elif hist < 0 and hist_rising:
        hist_score = -15
    else:
        hist_score = -50

    # Component 2: Line position + crossover (30%)
    # Check for fresh crossover (within last candle)
    cross_up = line_prev < signal_prev and line > signal
    cross_down = line_prev > signal_prev and line < signal

    if cross_up:
        pos_score = 50
    elif cross_down:
        pos_score = -50
    elif line > signal:
        pos_score = 30
    else:
        pos_score = -30

    # Component 3: MACD divergence (30%)
    macd_df = indicators.get("macd_df")
    close_series = indicators.get("close_series")
    lookback = config.get("indicators", {}).get("macd", {}).get("divergence_lookback", 30)

    div_type = "none"
    div_score = 0

    if macd_df is not None and close_series is not None:
        macd_hist_series = macd_df["macd_histogram"]
        div_type = detect_divergence(close_series, macd_hist_series, lookback=lookback)
        if div_type == "bullish":
            div_score = 60
        elif div_type == "hidden_bullish":
            div_score = 30
        elif div_type == "bearish":
            div_score = -60
        elif div_type == "hidden_bearish":
            div_score = -30

    total = 0.4 * hist_score + 0.3 * pos_score + 0.3 * div_score
    total = clamp(total)

    return {
        "score": round(total, 1),
        "histogram_score": hist_score,
        "position_score": pos_score,
        "divergence_type": div_type,
        "divergence_score": div_score,
        "cross_up": cross_up,
        "cross_down": cross_down,
    }


# ----------------------------------------------------------------
# Bollinger Bands Scoring
# ----------------------------------------------------------------
def score_bollinger(bb_data: dict) -> dict:
    """
    Score Bollinger Bands based on %B position.
    """
    pct_b = bb_data["percent_b"]
    squeeze = bb_data["squeeze"]

    if pct_b < 0.0:
        score = _interpolate(pct_b, -0.2, 0.0, 100, 80)
    elif pct_b < 0.2:
        score = _interpolate(pct_b, 0.0, 0.2, 80, 40)
    elif pct_b < 0.4:
        score = _interpolate(pct_b, 0.2, 0.4, 40, 0)
    elif pct_b < 0.6:
        score = _interpolate(pct_b, 0.4, 0.6, 10, -10)
    elif pct_b < 0.8:
        score = _interpolate(pct_b, 0.6, 0.8, 0, -40)
    elif pct_b < 1.0:
        score = _interpolate(pct_b, 0.8, 1.0, -40, -80)
    else:
        score = _interpolate(pct_b, 1.0, 1.2, -80, -100)

    score = clamp(score)

    return {
        "score": round(score, 1),
        "percent_b": round(pct_b, 4),
        "squeeze": squeeze,
    }
