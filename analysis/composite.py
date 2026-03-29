"""
Composite Score Calculator.
Combines all indicator scores with weights + RSI-BB confluence overlay.
Handles missing on-chain data with automatic weight redistribution.
"""
import logging
from typing import Optional

from analysis.technical_score import score_rsi, score_macd, score_bollinger, score_ema_cross, score_stoch_rsi, score_obv
from analysis.onchain_score import score_mvrv, score_sopr, score_exchange_netflow, score_funding_rate, score_fear_greed
from analysis.confluence import calculate_confluence

logger = logging.getLogger(__name__)


def clamp(value: float, lo: float = -100, hi: float = 100) -> float:
    return max(lo, min(hi, value))


def compute_tech_composite(indicators: dict, coin: str = "") -> dict:
    """
    Tech-only composite score for 4h timeframe scanning.
    No on-chain or sentiment data — just pure technicals.
    Returns a lightweight result dict.
    """
    weights_4h = {
        "rsi": 0.25,
        "macd": 0.20,
        "bollinger": 0.15,
        "ema": 0.20,
        "stoch_rsi": 0.15,
        "obv": 0.05,
    }

    rsi_result = score_rsi(indicators["rsi"], indicators, {})
    macd_result = score_macd(indicators["macd"], indicators, {})
    bb_result = score_bollinger(indicators["bb"])
    ema_result = score_ema_cross(indicators.get("ema"))
    stoch_result = score_stoch_rsi(indicators.get("stoch_rsi"))
    obv_result = score_obv(indicators.get("obv"))

    adx_value = indicators.get("adx")
    adx_mult = _calc_adx_multiplier(adx_value)

    score = 0.0
    score += rsi_result["total"] * weights_4h["rsi"] * adx_mult
    score += macd_result["score"] * weights_4h["macd"] * adx_mult
    score += bb_result["score"] * weights_4h["bollinger"] * adx_mult
    if ema_result:
        score += ema_result["score"] * weights_4h["ema"] * adx_mult
    if stoch_result:
        score += stoch_result["score"] * weights_4h["stoch_rsi"] * adx_mult
    if obv_result:
        score += obv_result["score"] * weights_4h["obv"]

    # RSI-BB confluence overlay (no config needed — use defaults)
    conf_config = {"confluence": {
        "rsi_oversold": 30, "rsi_overbought": 70,
        "bb_low_threshold": 0.2, "bb_high_threshold": 0.8,
        "confluence_bonus": 15, "conflict_penalty": 10, "squeeze_extra": 8,
    }}
    confluence_bonus, confluence_flag = calculate_confluence(
        rsi_value=indicators["rsi"],
        percent_b=indicators["bb"]["percent_b"],
        squeeze_active=indicators["bb"]["squeeze"],
        config=conf_config,
    )

    final = clamp(score + confluence_bonus)

    return {
        "coin": coin,
        "tech_score": round(final, 1),
        "price": float(indicators["close_series"].iloc[-1]),
        "rsi": rsi_result,
        "macd": macd_result,
        "bb": bb_result,
        "ema": ema_result,
        "stoch_rsi": stoch_result,
        "obv": obv_result,
        "adx": adx_value,
        "adx_multiplier": round(adx_mult, 2),
        "confluence_flag": confluence_flag,
        "timeframe": "4h",
    }


def compute_composite(
    indicators: dict,
    onchain_data: dict,
    funding_data: Optional[dict],
    config: dict,
    coin: str = "BTC",
) -> dict:
    weights = dict(config.get("weights", {}))

    # ================================================================
    # 1. TECHNICAL SCORES
    # ================================================================
    rsi_result = score_rsi(indicators["rsi"], indicators, config)
    macd_result = score_macd(indicators["macd"], indicators, config)
    bb_result = score_bollinger(indicators["bb"])

    # New technical indicators
    ema_result = score_ema_cross(indicators.get("ema"))
    stoch_result = score_stoch_rsi(indicators.get("stoch_rsi"))
    obv_result = score_obv(indicators.get("obv"))

    # ADX confidence multiplier (not scored, used to scale tech signals)
    adx_value = indicators.get("adx")
    adx_multiplier = _calc_adx_multiplier(adx_value)

    # ================================================================
    # 2. ON-CHAIN SCORES (with missing data handling)
    # ================================================================
    mvrv_result = None
    sopr_result = None
    exchange_result = None
    missing = []

    mvrv_z = onchain_data.get("mvrv_zscore")
    if mvrv_z is not None:
        mvrv_result = score_mvrv(mvrv_z)
    else:
        missing.append("mvrv")

    sopr_val = onchain_data.get("sopr")
    sopr_trend = onchain_data.get("sopr_trend", "unknown")
    if sopr_val is not None:
        sopr_result = score_sopr(sopr_val, sopr_trend)
    else:
        missing.append("sopr")

    netflow = onchain_data.get("exchange_netflow")
    if netflow is not None:
        exchange_result = score_exchange_netflow(netflow["netflow_24h"], netflow["netflow_7d"], coin)
    else:
        missing.append("exchange_flow")

    # ================================================================
    # 3. FUNDING RATE
    # ================================================================
    funding_result = None
    if funding_data and funding_data.get("avg_funding_rate") is not None:
        funding_result = score_funding_rate(funding_data["avg_funding_rate"])
    else:
        missing.append("funding_rate")

    # ================================================================
    # 4. SENTIMENT — Fear & Greed (global, same for all coins)
    # ================================================================
    fear_greed_result = None
    fg_value = onchain_data.get("fear_greed")
    if fg_value is not None:
        fear_greed_result = score_fear_greed(int(fg_value))
    else:
        missing.append("fear_greed")

    # Missing new tech indicators
    if ema_result is None:
        missing.append("ema")
    if stoch_result is None:
        missing.append("stoch_rsi")
    if obv_result is None:
        missing.append("obv")

    # ================================================================
    # 5. WEIGHT REDISTRIBUTION for missing data
    # ================================================================
    effective_weights = _redistribute_weights(weights, missing)

    # ================================================================
    # 6. WEIGHTED SUM
    # ================================================================
    base_score = 0.0

    # Technical (apply ADX multiplier to reduce noise in sideways market)
    tech_scale = adx_multiplier
    base_score += rsi_result["total"] * effective_weights.get("rsi", 0) * tech_scale
    base_score += macd_result["score"] * effective_weights.get("macd", 0) * tech_scale
    base_score += bb_result["score"] * effective_weights.get("bollinger", 0) * tech_scale

    if ema_result:
        base_score += ema_result["score"] * effective_weights.get("ema", 0) * tech_scale
    if stoch_result:
        base_score += stoch_result["score"] * effective_weights.get("stoch_rsi", 0) * tech_scale
    if obv_result:
        base_score += obv_result["score"] * effective_weights.get("obv", 0)

    # On-chain (no ADX scaling — macro data)
    if mvrv_result:
        base_score += mvrv_result["score"] * effective_weights.get("mvrv", 0)
    if sopr_result:
        base_score += sopr_result["score"] * effective_weights.get("sopr", 0)
    if exchange_result:
        base_score += exchange_result["score"] * effective_weights.get("exchange_flow", 0)

    # Derivatives
    if funding_result:
        base_score += funding_result["score"] * effective_weights.get("funding_rate", 0)

    # Sentiment
    if fear_greed_result:
        base_score += fear_greed_result["score"] * effective_weights.get("fear_greed", 0)

    # ================================================================
    # 7. RSI-BB CONFLUENCE OVERLAY
    # ================================================================
    confluence_bonus, confluence_flag = calculate_confluence(
        rsi_value=indicators["rsi"],
        percent_b=indicators["bb"]["percent_b"],
        squeeze_active=indicators["bb"]["squeeze"],
        config=config,
    )

    composite = clamp(base_score + confluence_bonus)

    # ================================================================
    # 8. ASSEMBLE RESULT
    # ================================================================
    return {
        "coin": coin,
        "composite_score": round(composite, 1),
        "base_score": round(base_score, 1),
        # Technical
        "rsi": rsi_result,
        "macd": macd_result,
        "bb": bb_result,
        "ema": ema_result,
        "stoch_rsi": stoch_result,
        "obv": obv_result,
        "adx": adx_value,
        # On-chain
        "mvrv": mvrv_result,
        "sopr": sopr_result,
        "exchange_flow": exchange_result,
        # Derivatives
        "funding": funding_result,
        # Sentiment
        "fear_greed": fear_greed_result,
        # Confluence
        "confluence_bonus": confluence_bonus,
        "confluence_flag": confluence_flag,
        # Meta
        "missing_indicators": missing,
        "effective_weights": effective_weights,
        "adx_multiplier": round(adx_multiplier, 2),
        "price": float(indicators["close_series"].iloc[-1]),
    }


def _calc_adx_multiplier(adx_value) -> float:
    """
    ADX confidence multiplier for technical scores.
    Weak trend (ADX < 20) → reduce tech signal confidence.
    Strong trend (ADX > 40) → full confidence.
    """
    if adx_value is None:
        return 1.0
    if adx_value < 15:
        return 0.65
    if adx_value < 20:
        return 0.80
    if adx_value < 30:
        return 0.90
    return 1.0


def _redistribute_weights(weights: dict, missing: list) -> dict:
    """
    Redistribute weights when indicators are missing.
    Missing weights distributed proportionally within same group.
    """
    if not missing:
        return dict(weights)

    effective = dict(weights)

    groups = {
        "technical": ["rsi", "macd", "bollinger", "ema", "stoch_rsi"],
        "volume": ["obv"],
        "onchain": ["mvrv", "sopr", "exchange_flow"],
        "derivatives": ["funding_rate"],
        "sentiment": ["fear_greed"],
    }

    for group_name, group_keys in groups.items():
        group_missing = [k for k in missing if k in group_keys]
        if not group_missing:
            continue

        group_present = [k for k in group_keys if k not in missing]
        if not group_present:
            # Entire group missing → redistribute to other groups
            total_missing_weight = sum(effective.get(k, 0) for k in group_missing)
            all_present = [k for k in effective if k not in missing and k not in group_keys]
            if all_present:
                per_key = total_missing_weight / len(all_present)
                for k in all_present:
                    effective[k] = effective.get(k, 0) + per_key
            for k in group_missing:
                effective[k] = 0
        else:
            # Partial group missing → redistribute within group
            missing_weight = sum(effective.get(k, 0) for k in group_missing)
            present_weight = sum(effective.get(k, 0) for k in group_present)
            if present_weight > 0:
                for k in group_present:
                    ratio = effective[k] / present_weight
                    effective[k] += missing_weight * ratio
            for k in group_missing:
                effective[k] = 0

    if missing:
        logger.info(f"Weight redistribution (missing: {missing}): "
                    f"{', '.join(f'{k}={v:.2%}' for k, v in effective.items() if v > 0)}")

    return effective
