"""
Scheduler: runs daily scan after 1D candle close and morning digest.
Uses APScheduler with AsyncIOScheduler.
"""
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
from telegram.constants import ParseMode

from signals.formatter import (
    format_scan_table,
    format_daily_digest,
    format_alert,
)

logger = logging.getLogger(__name__)


class BotScheduler:
    def __init__(self, app: Application, config: dict):
        self.app = app
        self.config = config
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.chat_id = None

    def start(self, chat_id: str):
        """Start the scheduler with scheduled jobs."""
        self.chat_id = chat_id
        sched_cfg = self.config.get("scheduler", {})

        # Daily scan after 1D candle close (default: 00:05 UTC)
        scan_time = sched_cfg.get("daily_scan_utc", "00:05")
        scan_h, scan_m = map(int, scan_time.split(":"))
        self.scheduler.add_job(
            self._daily_scan,
            CronTrigger(hour=scan_h, minute=scan_m),
            id="daily_scan",
            name="Daily Market Scan",
            replace_existing=True,
        )
        logger.info(f"Scheduled daily scan at {scan_time} UTC")

        # Daily digest (default: 09:00 UTC)
        digest_time = sched_cfg.get("daily_digest_utc", "09:00")
        digest_h, digest_m = map(int, digest_time.split(":"))
        self.scheduler.add_job(
            self._daily_digest,
            CronTrigger(hour=digest_h, minute=digest_m),
            id="daily_digest",
            name="Daily Digest",
            replace_existing=True,
        )
        logger.info(f"Scheduled daily digest at {digest_time} UTC")

        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        """Shutdown scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    async def _send_message(self, text: str):
        """Send a message to the configured chat."""
        if not self.chat_id:
            logger.error("No chat_id configured for scheduler")
            return
        try:
            bot = self.app.bot
            # Split long messages
            max_len = 4096
            if len(text) <= max_len:
                await bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            else:
                chunks = _split_text(text, max_len)
                for chunk in chunks:
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
        except Exception as e:
            logger.error(f"Failed to send scheduled message: {e}")

    async def _daily_scan(self):
        """Run full market scan and send alerts."""
        logger.info("Running scheduled daily scan...")
        scanner = self.app.bot_data.get("scanner")
        if not scanner:
            logger.error("Scanner not available for scheduled scan")
            return

        try:
            # Get previous results before scan
            previous = scanner.storage.get_all_previous_results()

            # Run scan
            results = scanner.scan_all()
            if not results:
                await self._send_message("❌ Ежедневный скан: нет данных")
                return

            # Send scan table
            text = format_scan_table(results, previous)
            await self._send_message(text)

            # Send alerts (no anti-spam)
            alerts_enabled = self.app.bot_data.get("alerts_enabled", True)
            if alerts_enabled:
                alerts = scanner.get_alerts(results)
                for alert, result in alerts:
                    alert_text = format_alert(alert, result)
                    await self._send_message(alert_text)

            logger.info(f"Daily scan complete: {len(results)} coins, {len(alerts) if alerts_enabled else 0} alerts")

        except Exception as e:
            logger.error(f"Daily scan error: {e}", exc_info=True)
            await self._send_message(f"❌ Ошибка ежедневного скана: {e}")

    async def _daily_digest(self):
        """Send morning digest."""
        digest_enabled = self.app.bot_data.get("digest_enabled", True)
        if not digest_enabled:
            logger.info("Daily digest is disabled, skipping")
            return

        logger.info("Sending daily digest...")
        scanner = self.app.bot_data.get("scanner")
        if not scanner:
            return

        try:
            previous = scanner.storage.get_all_previous_results()

            # Use cached results if recent, otherwise re-scan
            results = scanner.scan_all()
            if not results:
                await self._send_message("❌ Digest: нет данных")
                return

            text = format_daily_digest(results, previous)
            await self._send_message(text)
            logger.info("Daily digest sent")

        except Exception as e:
            logger.error(f"Digest error: {e}", exc_info=True)


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks by lines."""
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks
