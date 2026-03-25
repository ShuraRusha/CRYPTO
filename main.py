"""
CryptoSignal Bot — Entry Point
Loads configuration, environment variables, and starts the Telegram bot.
"""
import os
import sys
import logging
import yaml
from dotenv import load_dotenv

from bot.telegram_bot import create_bot


def setup_logging():
    """Configure logging to stdout and file."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    # Create logs directory
    os.makedirs("logs", exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
        ],
    )
    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def load_config(path: str = "config.yaml") -> dict:
    """Load YAML configuration."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def load_env() -> dict:
    """Load environment variables from .env file."""
    load_dotenv()
    env = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
        "CRYPTOQUANT_API_KEY": os.getenv("CRYPTOQUANT_API_KEY", ""),
    }
    return env


def validate_env(env: dict):
    """Validate required environment variables."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Copy .env.example to .env and fill in your values."
        )

    optional = ["CRYPTOQUANT_API_KEY"]
    missing_optional = [k for k in optional if not env.get(k)]
    if missing_optional:
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Optional API keys not set: {', '.join(missing_optional)}. "
            f"On-chain metrics will be unavailable."
        )


def main():
    """Main entry point."""
    # Setup
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("CryptoSignal Bot v2.1 starting...")
    logger.info("=" * 60)

    # Load config
    try:
        config = load_config()
        logger.info(f"Config loaded: {len(config.get('assets', []))} assets")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Load environment
    try:
        env = load_env()
        validate_env(env)
        logger.info("Environment variables loaded")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Create data directory for SQLite
    os.makedirs("data", exist_ok=True)

    # Create and run bot
    try:
        app = create_bot(config=config, env=env)
        logger.info("Starting Telegram bot (polling)...")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message"],
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
