"""
Unit tests for scoring functions.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.technical_score import score_rsi, score_macd, score_bollinger
from analysis.onchain_score import score_mvrv, score_sopr, score_exchange_netflow, score_funding_rate
from analysis.confluence import calculate_confluence


# ================================================================
# RSI Scoring Tests
# ================================================================
def test_rsi_extreme_oversold():
    indicators = {"rsi_series": None, "close_series": None}
    config = {"indicators": {"rsi": {"divergence_lookback": 30}}, "divergence": {}}
    result = score_rsi(10, indicators, config)
    assert result["total"] == 100, f"RSI=10 should give +100, got {result['total']}"

def test_rsi_oversold():
    indicators = {"rsi_series": None, "close_series": None}
    config = {"indicators": {"rsi": {"divergence_lookback": 30}}, "divergence": {}}
    result = score_rsi(25, indicators, config)
    assert 50 < result["total"] <= 100, f"RSI=25 should be +50 to +100, got {result['total']}"

def test_rsi_neutral():
    indicators = {"rsi_series": None, "close_series": None}
    config = {"indicators": {"rsi": {"divergence_lookback": 30}}, "divergence": {}}
    result = score_rsi(50, indicators, config)
    assert -10 <= result["total"] <= 10, f"RSI=50 should be ~0, got {result['total']}"

def test_rsi_overbought():
    indicators = {"rsi_series": None, "close_series": None}
    config = {"indicators": {"rsi": {"divergence_lookback": 30}}, "divergence": {}}
    result = score_rsi(80, indicators, config)
    assert -100 <= result["total"] < -50, f"RSI=80 should be negative, got {result['total']}"

def test_rsi_extreme_overbought():
    indicators = {"rsi_series": None, "close_series": None}
    config = {"indicators": {"rsi": {"divergence_lookback": 30}}, "divergence": {}}
    result = score_rsi(95, indicators, config)
    assert result["total"] == -100, f"RSI=95 should give -100, got {result['total']}"


# ================================================================
# MACD Scoring Tests
# ================================================================
def test_macd_bullish_cross():
    macd_data = {
        "histogram": 0.5, "histogram_prev": -0.2,
        "line": 1.0, "signal": 0.8,
        "line_prev": 0.7, "signal_prev": 0.9,  # cross up
    }
    indicators = {"macd_df": None, "close_series": None}
    config = {"indicators": {"macd": {"divergence_lookback": 30}}}
    result = score_macd(macd_data, indicators, config)
    assert result["score"] > 0, f"Bullish cross should be positive, got {result['score']}"
    assert result["cross_up"] is True

def test_macd_bearish():
    macd_data = {
        "histogram": -0.5, "histogram_prev": -0.2,
        "line": 0.5, "signal": 0.8,
        "line_prev": 0.6, "signal_prev": 0.7,
    }
    indicators = {"macd_df": None, "close_series": None}
    config = {"indicators": {"macd": {"divergence_lookback": 30}}}
    result = score_macd(macd_data, indicators, config)
    assert result["score"] < 0, f"Bearish MACD should be negative, got {result['score']}"


# ================================================================
# Bollinger Bands Scoring Tests
# ================================================================
def test_bb_at_bottom():
    result = score_bollinger({"percent_b": 0.05, "squeeze": False})
    assert result["score"] > 50, f"BB at bottom should be bullish, got {result['score']}"

def test_bb_at_top():
    result = score_bollinger({"percent_b": 0.95, "squeeze": False})
    assert result["score"] < -50, f"BB at top should be bearish, got {result['score']}"

def test_bb_center():
    result = score_bollinger({"percent_b": 0.5, "squeeze": False})
    assert -15 <= result["score"] <= 15, f"BB center should be neutral, got {result['score']}"


# ================================================================
# MVRV Scoring Tests
# ================================================================
def test_mvrv_undervalued():
    result = score_mvrv(-0.8)
    assert result["score"] == 100, f"MVRV Z < -0.5 should be +100, got {result['score']}"

def test_mvrv_overvalued():
    result = score_mvrv(8.0)
    assert result["score"] == -100, f"MVRV Z > 7 should be -100, got {result['score']}"

def test_mvrv_neutral():
    result = score_mvrv(1.0)
    assert 25 < result["score"] < 75, f"MVRV Z=1 should be moderate, got {result['score']}"


# ================================================================
# SOPR Scoring Tests
# ================================================================
def test_sopr_capitulation():
    result = score_sopr(0.93, "falling")
    assert result["score"] > 70, f"SOPR=0.93 falling should be strong bullish, got {result['score']}"

def test_sopr_profit_taking():
    result = score_sopr(1.08, "rising")
    assert result["score"] < -40, f"SOPR=1.08 rising should be bearish, got {result['score']}"

def test_sopr_neutral():
    result = score_sopr(1.0, "unknown")
    assert -15 <= result["score"] <= 15, f"SOPR=1.0 should be neutral, got {result['score']}"


# ================================================================
# Exchange Netflow Tests
# ================================================================
def test_netflow_outflow():
    result = score_exchange_netflow(-6000, -20000, "BTC")
    assert result["score"] > 70, f"Strong outflow should be bullish, got {result['score']}"

def test_netflow_inflow():
    result = score_exchange_netflow(6000, 20000, "BTC")
    assert result["score"] < -70, f"Strong inflow should be bearish, got {result['score']}"


# ================================================================
# Funding Rate Tests
# ================================================================
def test_funding_extreme_shorts():
    result = score_funding_rate(-0.0015)  # -0.15%
    assert result["score"] == 100, f"Extreme negative funding should be +100, got {result['score']}"

def test_funding_extreme_longs():
    result = score_funding_rate(0.0015)  # +0.15%
    assert result["score"] == -100, f"Extreme positive funding should be -100, got {result['score']}"

def test_funding_neutral():
    result = score_funding_rate(0.0001)  # +0.01%
    assert -15 <= result["score"] <= 15, f"Neutral funding, got {result['score']}"


# ================================================================
# RSI-BB Confluence Tests
# ================================================================
def test_confluence_bullish():
    config = {"confluence": {
        "rsi_oversold": 30, "rsi_overbought": 70,
        "bb_low_threshold": 0.2, "bb_high_threshold": 0.8,
        "confluence_bonus": 20, "conflict_penalty": 15, "squeeze_extra": 10,
    }}
    bonus, flag = calculate_confluence(25, 0.1, False, config)
    assert bonus == 20, f"Bullish confluence should give +20, got {bonus}"
    assert "🟢🟢" in flag

def test_confluence_bearish():
    config = {"confluence": {
        "rsi_oversold": 30, "rsi_overbought": 70,
        "bb_low_threshold": 0.2, "bb_high_threshold": 0.8,
        "confluence_bonus": 20, "conflict_penalty": 15, "squeeze_extra": 10,
    }}
    bonus, flag = calculate_confluence(75, 0.9, False, config)
    assert bonus == -20, f"Bearish confluence should give -20, got {bonus}"
    assert "🔴🔴" in flag

def test_confluence_conflict():
    config = {"confluence": {
        "rsi_oversold": 30, "rsi_overbought": 70,
        "bb_low_threshold": 0.2, "bb_high_threshold": 0.8,
        "confluence_bonus": 20, "conflict_penalty": 15, "squeeze_extra": 10,
    }}
    bonus, flag = calculate_confluence(75, 0.1, False, config)
    assert bonus == 15, f"Conflict should give +15, got {bonus}"
    assert "⚠️" in flag

def test_confluence_squeeze_combo():
    config = {"confluence": {
        "rsi_oversold": 30, "rsi_overbought": 70,
        "bb_low_threshold": 0.2, "bb_high_threshold": 0.8,
        "confluence_bonus": 20, "conflict_penalty": 15, "squeeze_extra": 10,
    }}
    bonus, flag = calculate_confluence(25, 0.1, True, config)
    assert bonus == 30, f"Squeeze + bullish confluence should give +30, got {bonus}"
    assert "SQUEEZE" in flag


# ================================================================
# Run all tests
# ================================================================
def run_all():
    tests = [
        test_rsi_extreme_oversold, test_rsi_oversold, test_rsi_neutral,
        test_rsi_overbought, test_rsi_extreme_overbought,
        test_macd_bullish_cross, test_macd_bearish,
        test_bb_at_bottom, test_bb_at_top, test_bb_center,
        test_mvrv_undervalued, test_mvrv_overvalued, test_mvrv_neutral,
        test_sopr_capitulation, test_sopr_profit_taking, test_sopr_neutral,
        test_netflow_outflow, test_netflow_inflow,
        test_funding_extreme_shorts, test_funding_extreme_longs, test_funding_neutral,
        test_confluence_bullish, test_confluence_bearish,
        test_confluence_conflict, test_confluence_squeeze_combo,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✅ {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {t.__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    return failed == 0


if __name__ == "__main__":
    print("Running CryptoSignal Bot tests...\n")
    success = run_all()
    sys.exit(0 if success else 1)
