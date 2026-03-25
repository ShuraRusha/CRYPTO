"""
Telegram bot command handlers.
All /commands are defined here and registered in telegram_bot.py.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from signals.formatter import (
    format_coin_detail,
    format_scan_table,
    format_top,
    format_alert,
)
from signals.classifier import classify_zone

logger = logging.getLogger(__name__)

# Max Telegram message length
TG_MAX_LEN = 4096


def _get_scanner(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data.get("scanner")


def _get_config(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data.get("config")


def _get_storage(context: ContextTypes.DEFAULT_TYPE):
    scanner = _get_scanner(context)
    return scanner.storage if scanner else None


async def _send(update: Update, text: str):
    """Send message, splitting if too long."""
    if len(text) <= TG_MAX_LEN:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        # Split by lines, respecting max length
        chunks = _split_message(text)
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def _split_message(text: str, max_len: int = TG_MAX_LEN) -> list[str]:
    """Split a long message into chunks."""
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


# ================================================================
# /start
# ================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    text = (
        "🤖 <b>CryptoSignal Bot v2.1</b>\n"
        "\n"
        "Бот анализирует 12 криптовалют по 7 индикаторам\n"
        "и даёт комбинированную оценку от -100 до +100.\n"
        "\n"
        "📊 <b>Индикаторы:</b>\n"
        "  Техника (30%): RSI, MACD, Bollinger Bands\n"
        "  On-chain (55%): MVRV, SOPR, Exchange Flow\n"
        "  Деривативы (15%): Funding Rate\n"
        "  + RSI-BB Confluence overlay\n"
        "\n"
        "📋 <b>Команды:</b>\n"
        "  /scan — Полный скан всех монет\n"
        "  /coin BTC — Детальный анализ монеты\n"
        "  /top — Топ бычьих и медвежьих\n"
        "  /alerts on|off — Push-уведомления\n"
        "  /digest on|off — Ежедневный дайджест\n"
        "  /weights — Текущие веса\n"
        "  /status — Статус бота\n"
        "  /help — Справка\n"
        "\n"
        "⚠️ Бот предоставляет информационный анализ,\n"
        "НЕ является финансовой рекомендацией."
    )
    await _send(update, text)


# ================================================================
# /scan
# ================================================================
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full scan of all 12 coins."""
    scanner = _get_scanner(context)
    if not scanner:
        await _send(update, "❌ Сканер не инициализирован.")
        return

    await _send(update, "⏳ Сканирую 12 монет... Это займёт 1-2 минуты.")

    try:
        results = scanner.scan_all()
        if not results:
            await _send(update, "❌ Не удалось получить данные ни по одной монете.")
            return

        previous = scanner.storage.get_all_previous_results()
        text = format_scan_table(results, previous)
        await _send(update, text)

        # Send alerts if any
        alerts_enabled = context.bot_data.get("alerts_enabled", True)
        if alerts_enabled:
            alerts = scanner.get_alerts(results)
            for alert, result in alerts:
                alert_text = format_alert(alert, result)
                await _send(update, alert_text)

    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        await _send(update, f"❌ Ошибка при сканировании: {e}")


# ================================================================
# /coin <TICKER>
# ================================================================
async def cmd_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed analysis of a single coin."""
    scanner = _get_scanner(context)
    if not scanner:
        await _send(update, "❌ Сканер не инициализирован.")
        return

    # Parse coin ticker
    args = context.args
    if not args:
        await _send(update, "⚠️ Укажи монету: /coin BTC")
        return

    ticker = args[0].upper()

    # Find matching asset in config
    asset = None
    for a in scanner.assets:
        if a["symbol"].startswith(ticker + "/"):
            asset = a
            break

    if not asset:
        available = ", ".join(a["symbol"].split("/")[0] for a in scanner.assets)
        await _send(update, f"⚠️ Монета {ticker} не найдена.\nДоступные: {available}")
        return

    await _send(update, f"⏳ Анализирую {ticker}...")

    try:
        symbol = asset["symbol"]
        name = asset.get("name", ticker)
        result = scanner.scan_coin(symbol, name, ticker)

        if not result:
            await _send(update, f"❌ Не удалось получить данные для {ticker}.")
            return

        previous = scanner.storage.get_previous_result(ticker)
        text = format_coin_detail(result, previous)
        await _send(update, text)

    except Exception as e:
        logger.error(f"Coin analysis error for {ticker}: {e}", exc_info=True)
        await _send(update, f"❌ Ошибка при анализе {ticker}: {e}")


# ================================================================
# /top
# ================================================================
async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top 3 bullish and top 3 bearish coins."""
    scanner = _get_scanner(context)
    if not scanner:
        await _send(update, "❌ Сканер не инициализирован.")
        return

    await _send(update, "⏳ Сканирую рынок...")

    try:
        results = scanner.scan_all()
        if not results:
            await _send(update, "❌ Нет данных.")
            return

        text = format_top(results)
        await _send(update, text)

    except Exception as e:
        logger.error(f"Top command error: {e}", exc_info=True)
        await _send(update, f"❌ Ошибка: {e}")


# ================================================================
# /alerts on|off
# ================================================================
async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle automatic push alerts."""
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        current = "✅ ВКЛ" if context.bot_data.get("alerts_enabled", True) else "❌ ВЫКЛ"
        await _send(update, f"📢 Автоалерты: {current}\nИспользуй: /alerts on или /alerts off")
        return

    enabled = args[0].lower() == "on"
    context.bot_data["alerts_enabled"] = enabled
    status = "✅ включены" if enabled else "❌ выключены"
    await _send(update, f"📢 Автоалерты {status}")


# ================================================================
# /digest on|off
# ================================================================
async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle daily digest."""
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        current = "✅ ВКЛ" if context.bot_data.get("digest_enabled", True) else "❌ ВЫКЛ"
        await _send(update, f"📰 Daily Digest: {current}\nИспользуй: /digest on или /digest off")
        return

    enabled = args[0].lower() == "on"
    context.bot_data["digest_enabled"] = enabled
    status = "✅ включён" if enabled else "❌ выключён"
    await _send(update, f"📰 Daily Digest {status}")


# ================================================================
# /weights
# ================================================================
async def cmd_weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current indicator weights."""
    config = _get_config(context)
    if not config:
        await _send(update, "❌ Конфигурация не загружена.")
        return

    weights = config.get("weights", {})

    tech_total = sum(weights.get(k, 0) for k in ["rsi", "macd", "bollinger"])
    onchain_total = sum(weights.get(k, 0) for k in ["mvrv", "sopr", "exchange_flow"])
    deriv_total = weights.get("funding_rate", 0)

    text = (
        "⚖️ <b>Текущие веса индикаторов</b>\n"
        "\n"
        f"📈 <b>Техника ({tech_total:.0%})</b>\n"
        f"  RSI:         {weights.get('rsi', 0):.0%}\n"
        f"  MACD:        {weights.get('macd', 0):.0%}\n"
        f"  Bollinger:   {weights.get('bollinger', 0):.0%}\n"
        "\n"
        f"⛓️ <b>On-chain ({onchain_total:.0%})</b>\n"
        f"  MVRV:        {weights.get('mvrv', 0):.0%}\n"
        f"  SOPR:        {weights.get('sopr', 0):.0%}\n"
        f"  Exch Flow:   {weights.get('exchange_flow', 0):.0%}\n"
        "\n"
        f"💹 <b>Деривативы ({deriv_total:.0%})</b>\n"
        f"  Funding:     {weights.get('funding_rate', 0):.0%}\n"
        "\n"
        "🔗 RSI-BB Confluence: ±30 (overlay)"
    )
    await _send(update, text)


# ================================================================
# /setweights
# ================================================================
async def cmd_setweights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change indicator weights. Example: /setweights RSI=20 MACD=15"""
    config = _get_config(context)
    if not config:
        await _send(update, "❌ Конфигурация не загружена.")
        return

    args = context.args
    if not args:
        await _send(
            update,
            "⚠️ Формат: /setweights RSI=20 MACD=15 BB=10 MVRV=20 SOPR=10 EXCHFLOW=15 FUNDING=10\n"
            "Сумма должна быть = 100",
        )
        return

    # Parse key=value pairs
    key_map = {
        "RSI": "rsi",
        "MACD": "macd",
        "BB": "bollinger",
        "BOLLINGER": "bollinger",
        "MVRV": "mvrv",
        "SOPR": "sopr",
        "EXCHFLOW": "exchange_flow",
        "EXCHANGE": "exchange_flow",
        "FUNDING": "funding_rate",
    }

    new_weights = dict(config.get("weights", {}))

    for arg in args:
        if "=" not in arg:
            continue
        key, val = arg.split("=", 1)
        key = key.upper()
        if key not in key_map:
            await _send(update, f"⚠️ Неизвестный индикатор: {key}")
            return
        try:
            new_weights[key_map[key]] = float(val) / 100.0
        except ValueError:
            await _send(update, f"⚠️ Некорректное значение: {val}")
            return

    # Validate sum
    total = sum(new_weights.values())
    if abs(total - 1.0) > 0.02:
        await _send(update, f"⚠️ Сумма весов = {total:.0%}, должна быть 100%")
        return

    config["weights"] = new_weights
    await _send(update, f"✅ Веса обновлены (сумма: {total:.0%}).\n/weights — проверить")


# ================================================================
# /status
# ================================================================
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot status information."""
    scanner = _get_scanner(context)
    config = _get_config(context)

    alerts_status = "✅" if context.bot_data.get("alerts_enabled", True) else "❌"
    digest_status = "✅" if context.bot_data.get("digest_enabled", True) else "❌"

    # API health check
    exchange_name = config.get("exchange", {}).get("primary", "bybit") if config else "?"
    num_assets = len(config.get("assets", [])) if config else 0

    # Last scan info
    storage = _get_storage(context)
    last_scan = "неизвестно"
    if storage:
        prev = storage.get_all_previous_results()
        if prev:
            last_scan = f"{len(prev)} монет в базе"

    text = (
        "🤖 <b>CryptoSignal Bot — Статус</b>\n"
        "\n"
        f"📡 Биржа: {exchange_name}\n"
        f"🪙 Монет: {num_assets}\n"
        f"📢 Алерты: {alerts_status}\n"
        f"📰 Дайджест: {digest_status}\n"
        f"💾 БД: {last_scan}\n"
        f"⏱ Скан: ежедневно 00:05 UTC\n"
        f"📰 Дайджест: 09:00 UTC\n"
        "\n"
        "📊 7 индикаторов + RSI-BB Confluence\n"
        "📐 Веса: Техника 30% │ On-chain 55% │ Деривативы 15%"
    )
    await _send(update, text)


# ================================================================
# /help
# ================================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all commands."""
    text = (
        "📋 <b>Команды CryptoSignal Bot</b>\n"
        "\n"
        "📊 <b>Анализ:</b>\n"
        "  /scan — Полный скан 12 монет\n"
        "  /coin BTC — Детальный анализ монеты\n"
        "  /top — Топ-3 бычьих и медвежьих\n"
        "\n"
        "🔔 <b>Уведомления:</b>\n"
        "  /alerts on|off — Push-алерты\n"
        "  /digest on|off — Ежедневный дайджест\n"
        "\n"
        "⚙️ <b>Настройки:</b>\n"
        "  /weights — Показать веса\n"
        "  /setweights RSI=13 MACD=9 ... — Изменить веса\n"
        "  /status — Статус бота\n"
        "\n"
        "💡 <b>Примеры:</b>\n"
        "  /coin ETH\n"
        "  /coin SOL\n"
        "  /setweights RSI=20 MACD=10 BB=10 MVRV=20 SOPR=10 EXCHFLOW=15 FUNDING=15"
    )
    await _send(update, text)
