"""
On-chain and derivatives scoring.
Maps MVRV Z-Score, SOPR, Exchange Netflow, Funding Rate → scores [-100, +100].
"""
import logging

logger = logging.getLogger(__name__)


def _interpolate(value: float, low: float, high: float, s_low: float, s_high: float) -> float:
    if high == low:
        return (s_low + s_high) / 2
    t = max(0.0, min(1.0, (value - low) / (high - low)))
    return s_low + t * (s_high - s_low)


def clamp(value: float, lo: float = -100, hi: float = 100) -> float:
    return max(lo, min(hi, value))


# ----------------------------------------------------------------
# MVRV Z-Score Scoring
# ----------------------------------------------------------------
def score_mvrv(z_score: float) -> dict:
    """
    MVRV Z-Score → Score.
    < -0.5  → +100 (strong undervalue)
    0       → +75
    2       → +25
    3.5     → -25
    7       → -100 (historic peak)
    > 7     → -100
    """
    if z_score < -0.5:
        score = 100.0
    elif z_score < 0:
        score = _interpolate(z_score, -0.5, 0, 100, 75)
    elif z_score < 2:
        score = _interpolate(z_score, 0, 2, 75, 25)
    elif z_score < 3.5:
        score = _interpolate(z_score, 2, 3.5, 25, -25)
    elif z_score < 7:
        score = _interpolate(z_score, 3.5, 7, -25, -100)
    else:
        score = -100.0

    return {
        "score": round(clamp(score), 1),
        "z_score": round(z_score, 3),
    }


# ----------------------------------------------------------------
# SOPR Scoring
# ----------------------------------------------------------------
def score_sopr(sopr_sma: float, sopr_trend: str = "unknown") -> dict:
    """
    SOPR (SMA7) → Score.
    sopr_trend: 'rising' or 'falling' or 'unknown'

    < 0.95 + falling → +80 to +100 (capitulation)
    < 1.0  + rising  → +40 to +80  (recovery from capitulation)
    0.98-1.02        → -10 to +10  (neutral)
    > 1.0  + falling → -40 to 0    (profit-taking slowing)
    > 1.05 + rising  → -60 to -100 (mass profit-taking)
    """
    if sopr_sma < 0.95:
        if sopr_trend == "falling":
            score = _interpolate(sopr_sma, 0.90, 0.95, 100, 80)
        else:
            score = _interpolate(sopr_sma, 0.90, 0.95, 80, 60)
    elif sopr_sma < 0.98:
        if sopr_trend == "rising":
            score = _interpolate(sopr_sma, 0.95, 0.98, 80, 40)
        else:
            score = _interpolate(sopr_sma, 0.95, 0.98, 60, 30)
    elif sopr_sma <= 1.02:
        score = _interpolate(sopr_sma, 0.98, 1.02, 10, -10)
    elif sopr_sma <= 1.05:
        if sopr_trend == "falling":
            score = _interpolate(sopr_sma, 1.02, 1.05, -10, -40)
        else:
            score = _interpolate(sopr_sma, 1.02, 1.05, -10, -60)
    else:
        if sopr_trend == "rising":
            score = _interpolate(sopr_sma, 1.05, 1.15, -60, -100)
        else:
            score = _interpolate(sopr_sma, 1.05, 1.15, -40, -80)

    return {
        "score": round(clamp(score), 1),
        "sopr_sma": round(sopr_sma, 4),
        "trend": sopr_trend,
    }


# ----------------------------------------------------------------
# Exchange Netflow Scoring
# ----------------------------------------------------------------
def score_exchange_netflow(netflow_24h: float, netflow_7d: float, coin: str = "BTC") -> dict:
    """
    Exchange Netflow → Score.
    Negative netflow (outflow) = bullish.
    Positive netflow (inflow) = bearish.

    Thresholds are coin-dependent (BTC in BTC units, ETH in ETH units, etc.)
    For simplicity, we use a normalized approach based on magnitude.
    """
    # Determine direction agreement
    both_outflow = netflow_24h < 0 and netflow_7d < 0
    both_inflow = netflow_24h > 0 and netflow_7d > 0

    # Score based on 24H with 7D confirmation
    abs_24h = abs(netflow_24h)

    # Dynamic thresholds by coin
    thresholds = _get_netflow_thresholds(coin)
    strong = thresholds["strong"]
    moderate = thresholds["moderate"]

    if netflow_24h < 0:  # Outflow = bullish
        if abs_24h >= strong:
            base = 85
        elif abs_24h >= moderate:
            base = 50
        else:
            base = 20
        # 7D confirmation
        if both_outflow:
            base = min(100, base + 15)
    elif netflow_24h > 0:  # Inflow = bearish
        if abs_24h >= strong:
            base = -85
        elif abs_24h >= moderate:
            base = -50
        else:
            base = -20
        if both_inflow:
            base = max(-100, base - 15)
    else:
        base = 0

    return {
        "score": round(clamp(base), 1),
        "netflow_24h": netflow_24h,
        "netflow_7d": netflow_7d,
    }


def _get_netflow_thresholds(coin: str) -> dict:
    """Return strong/moderate netflow thresholds per coin (in native units)."""
    # These are approximate — can be tuned with historical data
    thresholds = {
        "BTC": {"strong": 5000, "moderate": 2000},
        "ETH": {"strong": 80000, "moderate": 30000},
        "SOL": {"strong": 2000000, "moderate": 500000},
        "XRP": {"strong": 100000000, "moderate": 30000000},
        "BNB": {"strong": 200000, "moderate": 50000},
        "ADA": {"strong": 200000000, "moderate": 50000000},
        "DOGE": {"strong": 1000000000, "moderate": 200000000},
        "AVAX": {"strong": 2000000, "moderate": 500000},
        "LINK": {"strong": 5000000, "moderate": 1000000},
        "DOT": {"strong": 10000000, "moderate": 2000000},
        "NEAR": {"strong": 10000000, "moderate": 2000000},
        "TON": {"strong": 10000000, "moderate": 2000000},
    }
    return thresholds.get(coin, {"strong": 1000000, "moderate": 100000})


# ----------------------------------------------------------------
# Funding Rate Scoring
# ----------------------------------------------------------------
def score_funding_rate(avg_funding: float) -> dict:
    """
    Average Funding Rate (24H, 3 periods) → Score.
    
    Funding is a CONTRARIAN indicator:
      - Strongly positive funding → market overleveraged long → bearish signal
      - Strongly negative funding → market overleveraged short → bullish signal
    
    Thresholds (typical 8H funding rate):
      > +0.1%   → -100 (extreme longs, high liquidation risk)
      +0.05%    → -60
      +0.01%    → -10  (normal)
      0         → 0
      -0.01%    → +10
      -0.05%    → +60
      < -0.1%   → +100 (extreme shorts, short squeeze likely)
    """
    rate = avg_funding * 100  # Convert to percentage for easier reasoning

    if rate <= -0.10:
        score = 100.0
    elif rate <= -0.05:
        score = _interpolate(rate, -0.10, -0.05, 100, 60)
    elif rate <= -0.01:
        score = _interpolate(rate, -0.05, -0.01, 60, 10)
    elif rate <= 0.01:
        score = _interpolate(rate, -0.01, 0.01, 10, -10)
    elif rate <= 0.05:
        score = _interpolate(rate, 0.01, 0.05, -10, -60)
    elif rate <= 0.10:
        score = _interpolate(rate, 0.05, 0.10, -60, -100)
    else:
        score = -100.0

    # Determine label
    if rate > 0.05:
        label = "🔴 Лонги перегружены"
    elif rate > 0.01:
        label = "🟡 Умеренно бычий перекос"
    elif rate > -0.01:
        label = "⚪ Нейтральный"
    elif rate > -0.05:
        label = "🟡 Умеренно медвежий перекос"
    else:
        label = "🟢 Шорты перегружены"

    return {
        "score": round(clamp(score), 1),
        "avg_funding_pct": round(rate, 4),
        "label": label,
    }


# ----------------------------------------------------------------
# Fear & Greed Index Scoring
# ----------------------------------------------------------------
def score_fear_greed(index_value: int) -> dict:
    """
    Crypto Fear & Greed Index (0-100) → Score.
    CONTRARIAN indicator: fear = buy opportunity, greed = sell signal.

    0-25   Extreme Fear  → +80 to +100 (great buying zone)
    25-45  Fear          → +30 to +80
    45-55  Neutral       → -20 to +30
    55-75  Greed         → -30 to -80
    75-100 Extreme Greed → -80 to -100 (high risk zone)
    """
    v = index_value

    if v <= 25:
        score = _interpolate(v, 0, 25, 100, 80)
    elif v <= 45:
        score = _interpolate(v, 25, 45, 80, 30)
    elif v <= 55:
        score = _interpolate(v, 45, 55, 30, -20)
    elif v <= 75:
        score = _interpolate(v, 55, 75, -30, -80)
    else:
        score = _interpolate(v, 75, 100, -80, -100)

    if v <= 25:
        label = "Экстремальный страх — зона покупки"
    elif v <= 45:
        label = "Страх — осторожный интерес"
    elif v <= 55:
        label = "Нейтральный сентимент"
    elif v <= 75:
        label = "Жадность — осторожность"
    else:
        label = "Экстремальная жадность — риск коррекции"

    return {
        "score": round(clamp(score), 1),
        "value": v,
        "label": label,
    }
