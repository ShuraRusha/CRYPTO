"""
Core scanner: orchestrates data fetching, analysis, and signal generation.
Used by both scheduled tasks and on-demand commands.
"""
import logging
import urllib.request
import json
from typing import Optional

from data.fetcher_price import PriceFetcher
from data.fetcher_onchain import OnchainFetcher
from data.cache import Cache
from analysis.indicators import get_latest_indicators
from analysis.composite import compute_composite
from signals.classifier import AlertTrigger
from db.storage import Storage

logger = logging.getLogger(__name__)


def fetch_fear_greed_index() -> Optional[int]:
    """Fetch Fear & Greed index from alternative.me (free, no API key needed)."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            value = int(data["data"][0]["value"])
            logger.info(f"Fear & Greed index: {value}")
            return value
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
        return None


class Scanner:
    def __init__(self, config: dict, env: dict):
        self.config = config
        self.assets = config.get("assets", [])
        
        # Exchange
        exc_cfg = config.get("exchange", {})
        self.price_fetcher = PriceFetcher(
            primary=exc_cfg.get("primary", "bybit"),
            fallback=exc_cfg.get("fallback", "okx"),
        )
        self.timeframe = exc_cfg.get("timeframe", "1d")
        self.ohlcv_limit = exc_cfg.get("ohlcv_limit", 200)

        # On-chain (CryptoQuant PRO only)
        self.onchain_fetcher = OnchainFetcher(
            cryptoquant_key=env.get("CRYPTOQUANT_API_KEY", ""),
        )

        # Storage & cache
        self.storage = Storage()
        self.cache = Cache(default_ttl=3600)  # 1 hour cache
        self.alert_trigger = AlertTrigger(config)

    def scan_coin(self, symbol: str, coin_name: str, coin_ticker: str, fear_greed: Optional[int] = None) -> Optional[dict]:
        """Run full analysis on a single coin."""
        logger.info(f"Scanning {coin_ticker} ({symbol})...")

        # 1. Fetch OHLCV
        df = self.price_fetcher.fetch_ohlcv(
            symbol, timeframe=self.timeframe, limit=self.ohlcv_limit
        )
        if df is None or df.empty:
            logger.error(f"No price data for {symbol}")
            return None

        # 2. Compute technical indicators
        indicators = get_latest_indicators(df, self.config)
        if indicators is None:
            logger.error(f"Indicator computation failed for {symbol}")
            return None

        # 3. Fetch on-chain data
        onchain_data = {}
        try:
            mvrv = self.onchain_fetcher.fetch_mvrv_zscore(coin_ticker)
            if mvrv is not None:
                onchain_data["mvrv_zscore"] = mvrv

            sopr = self.onchain_fetcher.fetch_sopr(coin_ticker)
            if sopr is not None:
                onchain_data["sopr"] = sopr
                # Simple trend detection
                sopr_prev = self.onchain_fetcher.fetch_sopr(coin_ticker, sma_period=14)
                if sopr_prev is not None:
                    onchain_data["sopr_trend"] = "rising" if sopr > sopr_prev else "falling"

            netflow = self.onchain_fetcher.fetch_exchange_netflow(coin_ticker)
            if netflow is not None:
                onchain_data["exchange_netflow"] = netflow

        except Exception as e:
            logger.error(f"On-chain fetch error for {coin_ticker}: {e}")

        # Fear & Greed (passed from scan_all, fetched once per cycle)
        if fear_greed is not None:
            onchain_data["fear_greed"] = fear_greed

        # 4. Fetch funding rate
        funding_data = {}
        try:
            rates = self.price_fetcher.fetch_funding_rate(symbol)
            if rates and len(rates) > 0:
                # Average last N funding rates
                avg_periods = self.config.get("indicators", {}).get("funding", {}).get("avg_periods", 3)
                recent = rates[-avg_periods:] if len(rates) >= avg_periods else rates
                avg_rate = sum(r.get("fundingRate", 0) for r in recent) / len(recent)
                funding_data["avg_funding_rate"] = avg_rate
        except Exception as e:
            logger.error(f"Funding rate fetch error for {symbol}: {e}")

        # 5. Compute composite score
        result = compute_composite(
            indicators=indicators,
            onchain_data=onchain_data,
            funding_data=funding_data if funding_data else None,
            config=self.config,
            coin=coin_ticker,
        )

        # 6. Save to DB
        self.storage.save_result(result)

        return result

    def scan_all(self) -> list[dict]:
        """Scan all configured assets. Returns list of results."""
        # Fetch Fear & Greed once for the whole scan cycle
        fear_greed = fetch_fear_greed_index()

        results = []
        for asset in self.assets:
            symbol = asset["symbol"]
            ticker = symbol.split("/")[0]
            name = asset.get("name", ticker)

            result = self.scan_coin(symbol, name, ticker, fear_greed=fear_greed)
            if result:
                results.append(result)
            else:
                logger.warning(f"Scan failed for {ticker}, skipping")

        logger.info(f"Scan complete: {len(results)}/{len(self.assets)} coins analyzed")
        return results

    def get_alerts(self, results: list) -> list[tuple[dict, dict]]:
        """
        Check all results for alert conditions.
        Returns list of (alert_dict, result_dict) tuples.
        """
        previous = self.storage.get_all_previous_results()
        all_alerts = []

        for result in results:
            coin = result["coin"]
            prev = previous.get(coin)
            alerts = self.alert_trigger.check_alerts(result, prev)
            for alert in alerts:
                self.storage.log_alert(coin, alert["type"], alert["message"])
                all_alerts.append((alert, result))

        return all_alerts
