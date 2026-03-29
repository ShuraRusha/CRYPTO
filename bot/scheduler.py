"""
Scheduler: daily 1D scan + morning digest + 4h technical scan.
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
    format_4h_scan,
)

logger = logging.getLogger(__name__)


class BotScheduler:
    def __init__(self, app: Application, config: dict):
        self.app = app
        self.config = config
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.chat_id = None

    def start(self, chat_id: str):
        """Start the scheduler with all jobs."""
        self.chat_id = chat_id
        sched_cfg = self.config.get("scheduler", {})

        # Daily 1D scan after candle close (00:05 UTC)
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

        # Daily digest (09:00 UTC)
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

        # 4h technical scan — every 4 hours at :05 (skip 00:05 — covered by daily scan)
        self.scheduler.add_job(
            self._scan_4h,
            CronTrigger(hour="4,8,12,16,20", minute=5),
            id="scan_4h",
            name="4H Technical Scan",
            replace_existing=True,
        )
        logger.info("Scheduled 4h scan at 04:05, 08:05, 12:05, 16:05, 20:05 UTC")

        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    async def _send_message(self, text: str):
        if not self.chat_id:
            return
        try:
            bot = self.app.bot
            max_len = 4096
            if len(text) <= max_len:
                await bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            else:
                for chunk in _split_text(text, max_len):
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
        except Exception as e:
            logger.error(f"Failed to send scheduled message: {e}")

    async def _daily_scan(self):
        """Run full 1D market scan."""
        logger.info("Running scheduled daily scan...")
        scanner = self.app.bot_data.get("scanner")
        if not scanner:
            return
        try:
            previous = scanner.storage.get_all_previous_results()
            results = scanner.scan_all()
            if not results:
                await self._send_message("❌ Ежедневный скан: нет данных")
                return

            text = format_scan_table(results, previous)
            await self._send_message(text)

            alerts_enabled = self.app.bot_data.get("alerts_enabled", True)
            if alerts_enabled:
                alerts = scanner.get_alerts(results)
                for alert, result in alerts:
                    await self._send_message(format_alert(alert, result))

            logger.info(f"Daily scan complete: {len(results)} coins")
        except Exception as e:
            logger.error(f"Daily scan error: {e}", exc_info=True)
            await self._send_message(f"❌ Ошибка скана: {e}")

    async def _daily_digest(self):
        """Send morning digest."""
        if not self.app.bot_data.get("digest_enabled", True):
            return
        logger.info("Sending daily digest...")
        scanner = self.app.bot_data.get("scanner")
        if not scanner:
            return
        try:
            previous = scanner.storage.get_all_previous_results()
            results = scanner.scan_all()
            if not results:
                await self._send_message("❌ Digest: нет данных")
                return
            text = format_daily_digest(results, previous)
            await self._send_message(text)
            logger.info("Daily digest sent")
        except Exception as e:
            logger.error(f"Digest error: {e}", exc_info=True)

    async def _scan_4h(self):
        """Run 4h technical scan and send confirmed signals."""
        logger.info("Running 4h technical scan...")
        scanner = self.app.bot_data.get("scanner")
        if not scanner:
            return
        try:
            results_4h = scanner.scan_all_4h()
            if not results_4h:
                return

            # Get 1D macro scores from DB for two-layer validation
            daily = scanner.storage.get_all_previous_results()
            daily_scores = {
                coin: data.get("composite_score", 0)
                for coin, data in daily.items()
            }

            text = format_4h_scan(results_4h, daily_scores)
            await self._send_message(text)
            logger.info("4h scan sent")
        except Exception as e:
            logger.error(f"4h scan error: {e}", exc_info=True)


def _split_text(text: str, max_len: int) -> list[str]:
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
