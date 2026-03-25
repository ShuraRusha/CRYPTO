"""
Signal classifier: composite score → zone.
Alert trigger: decides which events warrant a Telegram notification.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Zone definitions (score thresholds)
ZONES = [
    {"name": "STRONG BUY",    "emoji": "🟢🟢", "min": 70,  "max": 100},
    {"name": "ACCUMULATION",  "emoji": "🟢",   "min": 40,  "max": 70},
    {"name": "SLIGHTLY BULL", "emoji": "🟡↑",  "min": 10,  "max": 40},
    {"name": "NEUTRAL",       "emoji": "⚪",    "min": -10, "max": 10},
    {"name": "SLIGHTLY BEAR", "emoji": "🟡↓",  "min": -40, "max": -10},
    {"name": "DISTRIBUTION",  "emoji": "🔴",   "min": -70, "max": -40},
    {"name": "STRONG SELL",   "emoji": "🔴🔴", "min": -100,"max": -70},
]


def classify_zone(score: float) -> dict:
    """Classify a composite score into a zone."""
    for zone in ZONES:
        if zone["min"] <= score <= zone["max"]:
            return zone
        # Handle edge: score exactly at boundary
        if score >= zone["min"] and score < zone["max"]:
            return zone
    # Fallback for extreme values
    if score >= 70:
        return ZONES[0]
    return ZONES[-1]


def get_trend_arrow(current_score: float, previous_score: Optional[float]) -> str:
    """Get trend arrow based on score change."""
    if previous_score is None:
        return "→"
    diff = current_score - previous_score
    if diff > 5:
        return "↗️"
    elif diff < -5:
        return "↘️"
    return "→"


# ----------------------------------------------------------------
# Alert Triggers
# ----------------------------------------------------------------
class AlertTrigger:
    """Determines which events should generate alerts."""

    def __init__(self, config: dict):
        self.zones_cfg = config.get("zones", {})

    def check_alerts(
        self,
        result: dict,
        previous_result: Optional[dict] = None,
    ) -> list[dict]:
        """
        Check all alert conditions for a coin analysis result.
        Returns list of alert dicts: [{type, priority, message}, ...]
        No anti-spam — all alerts are delivered.
        """
        alerts = []
        score = result["composite_score"]
        coin = result["coin"]
        zone = classify_zone(score)

        # 1. Strong signal
        if abs(score) >= 70:
            priority = "🔴 HIGH"
            alerts.append({
                "type": "strong_signal",
                "priority": priority,
                "message": f"{zone['emoji']} {zone['name']} — {coin} (Score: {score:+.0f})",
            })

        # 2. Zone change
        if previous_result:
            prev_zone = classify_zone(previous_result["composite_score"])
            if prev_zone["name"] != zone["name"]:
                alerts.append({
                    "type": "zone_change",
                    "priority": "🟡 MEDIUM",
                    "message": (
                        f"📊 Смена зоны {coin}: "
                        f"{prev_zone['emoji']} {prev_zone['name']} → "
                        f"{zone['emoji']} {zone['name']}"
                    ),
                })

        # 3. RSI-BB Confluence
        if result.get("confluence_flag"):
            alerts.append({
                "type": "confluence",
                "priority": "🟡 MEDIUM",
                "message": f"🔗 {coin}: {result['confluence_flag']}",
            })

        # 4. RSI Divergence
        rsi = result.get("rsi", {})
        if rsi.get("divergence_type", "none") != "none":
            alerts.append({
                "type": "rsi_divergence",
                "priority": "🟡 MEDIUM",
                "message": f"📈 {coin}: {rsi['divergence_label']} (RSI)",
            })

        # 5. MACD Divergence
        macd = result.get("macd", {})
        if macd.get("divergence_type", "none") != "none":
            from analysis.divergence import divergence_label
            label = divergence_label(macd["divergence_type"])
            alerts.append({
                "type": "macd_divergence",
                "priority": "🟡 MEDIUM",
                "message": f"📈 {coin}: {label} (MACD)",
            })

        # 6. Extreme on-chain
        mvrv = result.get("mvrv")
        if mvrv and (mvrv["z_score"] > 7 or mvrv["z_score"] < -0.5):
            alerts.append({
                "type": "extreme_onchain",
                "priority": "🔴 HIGH",
                "message": f"⛓️ {coin}: MVRV Z-Score экстремальный ({mvrv['z_score']:.2f})",
            })

        # 7. Extreme funding
        funding = result.get("funding")
        if funding and abs(funding["avg_funding_pct"]) > 0.05:
            alerts.append({
                "type": "extreme_funding",
                "priority": "🟡 MEDIUM",
                "message": f"💹 {coin}: Funding Rate {funding['label']} ({funding['avg_funding_pct']:.4f}%)",
            })

        return alerts
