"""
RSI-BB Confluence Module.
Links RSI and Bollinger Bands to produce bonus/penalty when they agree or conflict.
"""
import logging

logger = logging.getLogger(__name__)


def calculate_confluence(
    rsi_value: float,
    percent_b: float,
    squeeze_active: bool,
    config: dict,
) -> tuple[int, str]:
    """
    Calculate RSI-BB confluence bonus and generate flag text.

    Returns:
        (bonus: int, flag: str)
        bonus is added to composite score
        flag is text for Telegram alert
    """
    conf_cfg = config.get("confluence", {})
    rsi_oversold = conf_cfg.get("rsi_oversold", 30)
    rsi_overbought = conf_cfg.get("rsi_overbought", 70)
    bb_low = conf_cfg.get("bb_low_threshold", 0.2)
    bb_high = conf_cfg.get("bb_high_threshold", 0.8)
    confluence_bonus = conf_cfg.get("confluence_bonus", 20)
    conflict_penalty = conf_cfg.get("conflict_penalty", 15)
    squeeze_extra = conf_cfg.get("squeeze_extra", 10)

    bonus = 0
    flag = ""

    rsi_is_oversold = rsi_value < rsi_oversold
    rsi_is_overbought = rsi_value > rsi_overbought
    bb_is_low = percent_b < bb_low
    bb_is_high = percent_b > bb_high

    # ---- CONFLUENCE (both agree) ----

    # RSI oversold + BB at bottom → strong bullish
    if rsi_is_oversold and bb_is_low:
        bonus = +confluence_bonus
        flag = "🟢🟢 RSI-BB CONFLUENCE (бычья)"

    # RSI overbought + BB at top → strong bearish
    elif rsi_is_overbought and bb_is_high:
        bonus = -confluence_bonus
        flag = "🔴🔴 RSI-BB CONFLUENCE (медвежья)"

    # ---- CONFLICT (they disagree) ----

    # RSI overbought but BB says price is at bottom
    elif rsi_is_overbought and bb_is_low:
        bonus = +conflict_penalty  # weakens bearish RSI signal
        flag = "⚠️ RSI-BB КОНФЛИКТ (RSI медведь, BB бык)"

    # RSI oversold but BB says price is at top
    elif rsi_is_oversold and bb_is_high:
        bonus = -conflict_penalty  # weakens bullish RSI signal
        flag = "⚠️ RSI-BB КОНФЛИКТ (RSI бык, BB медведь)"

    # ---- SQUEEZE COMBO ----
    if squeeze_active and abs(bonus) >= confluence_bonus:
        extra = squeeze_extra if bonus > 0 else -squeeze_extra
        bonus += extra
        flag += " + ⚡ SQUEEZE"

        if bonus > 0:
            logger.info(f"SQUEEZE + BULLISH CONFLUENCE: bonus={bonus}")
        else:
            logger.info(f"SQUEEZE + BEARISH CONFLUENCE: bonus={bonus}")

    return bonus, flag
