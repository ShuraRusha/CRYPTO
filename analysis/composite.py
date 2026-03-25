"""
Composite Score Calculator.
Combines all indicator scores with weights + RSI-BB confluence overlay.
Handles missing on-chain data with automatic weight redistribution.
"""
import logging
from typing import Optional

from analysis.technical_score import score_rsi, score_macd, score_bollinger
from analysis.onchain_score import score_mvrv, score_sopr, score_exchange_netflow, score_funding_rate
from analysis.confluence import calculate_confluence

logger = logging.getLogger(__name__)


def clamp(value: float, lo: float = -100, hi: float = 100) -> float:
    return max(lo, min(hi, value))


def compute_composite(
    indicators: dict,
    onchain_data: dict,
    funding_data: Optional[dict],
    config: dict,
    coin: str = "BTC",
) -> dict:
    """
    Compute the final composite score for a coin.

    Args:
        indicators: dict from analysis.indicators.get_latest_indicators()
        onchain_data: {mvrv_zscore, sopr, exchange_netflow}
        funding_data: {avg_funding_rate} or None
        config: full config dict
        coin: coin ticker (e.g. "BTC")

    Returns:
        Full analysis result dict with all scores and metadata.
    """
    weights = dict(config.get("weights", {}))

    # ================================================================
    # 1. TECHNICAL SCORES
    # ================================================================
    rsi_result = score_rsi(indicators["rsi"], indicators, config)
    macd_result = score_macd(indicators["macd"], indicators, config)
    bb_result = score_bollinger(indicators["bb"])

    # ================================================================
    # 2. ON-CHAIN SCORES (with missing data handling)
    # ================================================================
    mvrv_result = None
    sopr_result = None
    exchange_result = None
    missing_onchain = []

    # MVRV Z-Score
    mvrv_z = onchain_data.get("mvrv_zscore")
    if mvrv_z is not None:
        mvrv_result = score_mvrv(mvrv_z)
    else:
        missing_onchain.append("mvrv")

    # SOPR
    sopr_val = onchain_data.get("sopr")
    sopr_trend = onchain_data.get("sopr_trend", "unknown")
    if sopr_val is not None:
        sopr_result = score_sopr(sopr_val, sopr_trend)
    else:
        missing_onchain.append("sopr")

    # Exchange Netflow
    netflow = onchain_data.get("exchange_netflow")
    if netflow is not None:
        exchange_result = score_exchange_netflow(
            netflow["netflow_24h"], netflow["netflow_7d"], coin
        )
    else:
        missing_onchain.append("exchange_flow")

    # ================================================================
    # 3. FUNDING RATE SCORE
    # ================================================================
    funding_result = None
    if funding_data and funding_data.get("avg_funding_rate") is not None:
        funding_result = score_funding_rate(funding_data["avg_funding_rate"])
    else:
        missing_onchain.append("funding_rate")

    # ================================================================
    # 4. WEIGHT REDISTRIBUTION for missing data
    # ================================================================
    effective_weights = _redistribute_weights(weights, missing_onchain)

    # ================================================================
    # 5. WEIGHTED SUM
    # ================================================================
    components = {}
    base_score = 0.0

    # Technical
    components["rsi"] = rsi_result["total"]
    base_score += rsi_result["total"] * effective_weights.get("rsi", 0)

    components["macd"] = macd_result["score"]
    base_score += macd_result["score"] * effective_weights.get("macd", 0)

    components["bollinger"] = bb_result["score"]
    base_score += bb_result["score"] * effective_weights.get("bollinger", 0)

    # On-chain
    if mvrv_result:
        components["mvrv"] = mvrv_result["score"]
        base_score += mvrv_result["score"] * effective_weights.get("mvrv", 0)

    if sopr_result:
        components["sopr"] = sopr_result["score"]
        base_score += sopr_result["score"] * effective_weights.get("sopr", 0)

    if exchange_result:
        components["exchange_flow"] = exchange_result["score"]
        base_score += exchange_result["score"] * effective_weights.get("exchange_flow", 0)

    # Derivatives
    if funding_result:
        components["funding_rate"] = funding_result["score"]
        base_score += funding_result["score"] * effective_weights.get("funding_rate", 0)

    # ================================================================
    # 6. RSI-BB CONFLUENCE OVERLAY
    # ================================================================
    confluence_bonus, confluence_flag = calculate_confluence(
        rsi_value=indicators["rsi"],
        percent_b=indicators["bb"]["percent_b"],
        squeeze_active=indicators["bb"]["squeeze"],
        config=config,
    )

    composite = clamp(base_score + confluence_bonus)

    # ================================================================
    # 7. ASSEMBLE RESULT
    # ================================================================
    return {
        "coin": coin,
        "composite_score": round(composite, 1),
        "base_score": round(base_score, 1),
        # Individual results
        "rsi": rsi_result,
        "macd": macd_result,
        "bb": bb_result,
        "mvrv": mvrv_result,
        "sopr": sopr_result,
        "exchange_flow": exchange_result,
        "funding": funding_result,
        # Confluence
        "confluence_bonus": confluence_bonus,
        "confluence_flag": confluence_flag,
        # Meta
        "missing_indicators": missing_onchain,
        "effective_weights": effective_weights,
        "price": float(indicators["close_series"].iloc[-1]),
    }


def _redistribute_weights(weights: dict, missing: list) -> dict:
    """
    Redistribute weights when on-chain indicators are missing.
    Missing weights are distributed proportionally among remaining indicators
    within the same group.
    """
    if not missing:
        return dict(weights)

    effective = dict(weights)
    
    # Group definitions
    groups = {
        "technical": ["rsi", "macd", "bollinger"],
        "onchain": ["mvrv", "sopr", "exchange_flow"],
        "derivatives": ["funding_rate"],
    }

    for group_name, group_keys in groups.items():
        group_missing = [k for k in missing if k in group_keys]
        if not group_missing:
            continue

        group_present = [k for k in group_keys if k not in missing]
        if not group_present:
            # Entire group is missing → redistribute to other groups
            total_missing_weight = sum(effective.get(k, 0) for k in group_missing)
            all_present = [
                k for k in effective
                if k not in missing and k not in group_keys
            ]
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

    # Log redistribution
    if missing:
        logger.info(
            f"Weight redistribution (missing: {missing}): "
            f"{', '.join(f'{k}={v:.2%}' for k, v in effective.items() if v > 0)}"
        )

    return effective
