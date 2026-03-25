"""
Telegram bot initialization.
Creates Application, registers handlers, injects dependencies.
"""
import logging
from telegram.ext import Application, CommandHandler

from bot.handlers import (
    cmd_start,
    cmd_scan,
    cmd_coin,
    cmd_top,
    cmd_alerts,
    cmd_digest,
    cmd_weights,
    cmd_setweights,
    cmd_status,
    cmd_help,
)
from bot.scanner import Scanner
from bot.scheduler import BotScheduler

logger = logging.getLogger(__name__)


def create_bot(config: dict, env: dict) -> Application:
    """
    Create and configure the Telegram bot application.

    Args:
        config: Parsed config.yaml
        env: Environment variables dict

    Returns:
        Configured Application (not yet running)
    """
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required in .env")

    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required in .env")

    # Build application
    app = Application.builder().token(token).build()

    # Initialize scanner (core analysis engine)
    scanner = Scanner(config=config, env=env)

    # Store shared objects in bot_data
    app.bot_data["scanner"] = scanner
    app.bot_data["config"] = config
    app.bot_data["chat_id"] = chat_id
    app.bot_data["alerts_enabled"] = True
    app.bot_data["digest_enabled"] = True

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("coin", cmd_coin))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("weights", cmd_weights))
    app.add_handler(CommandHandler("setweights", cmd_setweights))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("Bot application created with all handlers registered")

    # Initialize scheduler
    bot_scheduler = BotScheduler(app=app, config=config)
    app.bot_data["scheduler"] = bot_scheduler

    # Register post_init to start scheduler after bot is ready
    async def post_init(application: Application):
        bot_scheduler.start(chat_id=chat_id)
        logger.info("Bot is ready and scheduler is running")
        # Send startup message
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🤖 <b>CryptoSignal Bot запущен!</b>\n"
                    "\n"
                    "📊 7 индикаторов │ 12 монет │ 1D таймфрейм\n"
                    "⏱ Скан: 00:05 UTC │ Дайджест: 09:00 UTC\n"
                    "\n"
                    "Используй /help для списка команд."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")

    async def post_shutdown(application: Application):
        sched = application.bot_data.get("scheduler")
        if sched:
            sched.stop()
        logger.info("Bot shutdown complete")

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    return app
