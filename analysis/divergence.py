"""
Divergence detection for RSI and MACD.
Detects regular and hidden divergences using swing highs/lows.
"""
import numpy as np
import pandas as pd
import logging
from scipy.signal import argrelextrema
from typing import Optional

logger = logging.getLogger(__name__)

# Divergence types
BULLISH_DIV = "bullish"
HIDDEN_BULLISH_DIV = "hidden_bullish"
BEARISH_DIV = "bearish"
HIDDEN_BEARISH_DIV = "hidden_bearish"
NO_DIV = "none"


def find_swing_points(series: pd.Series, order: int = 5) -> dict:
    """
    Find swing highs and swing lows in a series.
    `order` = number of candles on each side to compare.
    Returns dict with 'highs' and 'lows' as lists of (index, value).
    """
    values = series.values
    
    high_indices = argrelextrema(values, np.greater_equal, order=order)[0]
    low_indices = argrelextrema(values, np.less_equal, order=order)[0]

    highs = [(int(i), float(values[i])) for i in high_indices]
    lows = [(int(i), float(values[i])) for i in low_indices]

    return {"highs": highs, "lows": lows}


def detect_divergence(
    price_series: pd.Series,
    indicator_series: pd.Series,
    lookback: int = 30,
    swing_order: int = 5,
) -> str:
    """
    Detect divergence between price and an indicator (RSI or MACD).
    
    Returns one of:
      'bullish'        — price: lower low,  indicator: higher low
      'hidden_bullish' — price: higher low,  indicator: lower low
      'bearish'        — price: higher high, indicator: lower high
      'hidden_bearish' — price: lower high,  indicator: higher high
      'none'           — no divergence detected
    """
    if len(price_series) < lookback or len(indicator_series) < lookback:
        return NO_DIV

    # Take last N candles
    price = price_series.iloc[-lookback:].reset_index(drop=True)
    indicator = indicator_series.iloc[-lookback:].reset_index(drop=True)

    price_swings = find_swing_points(price, order=swing_order)
    ind_swings = find_swing_points(indicator, order=swing_order)

    # --- Check for BULLISH divergence (using lows) ---
    div_type = _check_low_divergence(price_swings["lows"], ind_swings["lows"])
    if div_type != NO_DIV:
        return div_type

    # --- Check for BEARISH divergence (using highs) ---
    div_type = _check_high_divergence(price_swings["highs"], ind_swings["highs"])
    if div_type != NO_DIV:
        return div_type

    return NO_DIV


def _check_low_divergence(price_lows: list, ind_lows: list) -> str:
    """Check bullish / hidden bullish divergence using swing lows."""
    if len(price_lows) < 2 or len(ind_lows) < 2:
        return NO_DIV

    # Take last 2 significant lows
    p1_idx, p1_val = price_lows[-2]
    p2_idx, p2_val = price_lows[-1]
    i1_idx, i1_val = ind_lows[-2]
    i2_idx, i2_val = ind_lows[-1]

    # Ensure they roughly correspond (not too far apart)
    if abs(p1_idx - i1_idx) > 10 or abs(p2_idx - i2_idx) > 10:
        return NO_DIV

    # Regular bullish: price lower low, indicator higher low
    if p2_val < p1_val and i2_val > i1_val:
        logger.info(
            f"Bullish divergence: price {p1_val:.2f}→{p2_val:.2f}, "
            f"indicator {i1_val:.2f}→{i2_val:.2f}"
        )
        return BULLISH_DIV

    # Hidden bullish: price higher low, indicator lower low
    if p2_val > p1_val and i2_val < i1_val:
        logger.info(
            f"Hidden bullish divergence: price {p1_val:.2f}→{p2_val:.2f}, "
            f"indicator {i1_val:.2f}→{i2_val:.2f}"
        )
        return HIDDEN_BULLISH_DIV

    return NO_DIV


def _check_high_divergence(price_highs: list, ind_highs: list) -> str:
    """Check bearish / hidden bearish divergence using swing highs."""
    if len(price_highs) < 2 or len(ind_highs) < 2:
        return NO_DIV

    p1_idx, p1_val = price_highs[-2]
    p2_idx, p2_val = price_highs[-1]
    i1_idx, i1_val = ind_highs[-2]
    i2_idx, i2_val = ind_highs[-1]

    if abs(p1_idx - i1_idx) > 10 or abs(p2_idx - i2_idx) > 10:
        return NO_DIV

    # Regular bearish: price higher high, indicator lower high
    if p2_val > p1_val and i2_val < i1_val:
        logger.info(
            f"Bearish divergence: price {p1_val:.2f}→{p2_val:.2f}, "
            f"indicator {i1_val:.2f}→{i2_val:.2f}"
        )
        return BEARISH_DIV

    # Hidden bearish: price lower high, indicator higher high
    if p2_val < p1_val and i2_val > i1_val:
        logger.info(
            f"Hidden bearish divergence: price {p1_val:.2f}→{p2_val:.2f}, "
            f"indicator {i1_val:.2f}→{i2_val:.2f}"
        )
        return HIDDEN_BEARISH_DIV

    return NO_DIV


def get_divergence_bonus(div_type: str, config: dict) -> int:
    """Map divergence type to score bonus from config."""
    div_cfg = config.get("divergence", {})
    bonuses = {
        BULLISH_DIV: div_cfg.get("rsi_bullish", 25),
        HIDDEN_BULLISH_DIV: div_cfg.get("rsi_hidden_bullish", 15),
        BEARISH_DIV: div_cfg.get("rsi_bearish", -25),
        HIDDEN_BEARISH_DIV: div_cfg.get("rsi_hidden_bearish", -15),
        NO_DIV: 0,
    }
    return bonuses.get(div_type, 0)


def divergence_label(div_type: str) -> str:
    """Human-readable label for Telegram messages."""
    labels = {
        BULLISH_DIV: "🔀 Бычья дивергенция",
        HIDDEN_BULLISH_DIV: "🔀 Скрытая бычья дивергенция",
        BEARISH_DIV: "🔀 Медвежья дивергенция",
        HIDDEN_BEARISH_DIV: "🔀 Скрытая медвежья дивергенция",
        NO_DIV: "",
    }
    return labels.get(div_type, "")
