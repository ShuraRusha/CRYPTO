# 🤖 CryptoSignal Bot v2.1

Telegram-бот для анализа крипторынка по 7 индикаторам с комбинированной оценкой.

## Возможности

- **12 монет**: BTC, ETH, SOL, XRP, BNB, ADA, DOGE, AVAX, LINK, DOT, NEAR, TON
- **7 индикаторов**: RSI (+дивергенция), MACD, Bollinger Bands, MVRV Z-Score, SOPR, Exchange Netflow, Funding Rate
- **RSI-BB Confluence**: бонус при совпадении RSI и Bollinger Bands
- **Composite Score**: от -100 до +100, автоматическая классификация по зонам
- **Автоматические алерты**: без антиспама, все сигналы доставляются
- **Ежедневный скан**: после закрытия дневной свечи (00:05 UTC)
- **Daily Digest**: утренняя сводка (09:00 UTC)

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo_url>
cd crypto-signal-bot
```

### 2. Создать виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Настроить .env

```bash
cp .env.example .env
```

Заполнить в `.env`:

```
TELEGRAM_BOT_TOKEN=...     # Получить у @BotFather в Telegram
TELEGRAM_CHAT_ID=...       # ID чата (можно узнать через @userinfobot)
CRYPTOQUANT_API_KEY=...    # PRO ключ с cryptoquant.com
```

### 4. Запустить

```bash
python main.py
```

### 5. Использовать в Telegram

Отправь боту `/start` и используй команды:

| Команда | Описание |
|---------|----------|
| `/scan` | Полный скан 12 монет |
| `/coin BTC` | Детальный анализ монеты |
| `/top` | Топ-3 бычьих и медвежьих |
| `/alerts on\|off` | Push-уведомления |
| `/digest on\|off` | Ежедневный дайджест |
| `/weights` | Текущие веса индикаторов |
| `/setweights RSI=20 MACD=10 ...` | Изменить веса |
| `/status` | Статус бота |

## Индикаторы и веса

| # | Индикатор | Группа | Вес |
|---|-----------|--------|-----|
| 1 | RSI (+ дивергенция) | Техника | 13% |
| 2 | MACD | Техника | 9% |
| 3 | Bollinger Bands | Техника | 8% |
| 4 | MVRV Z-Score | On-chain | 22% |
| 5 | SOPR | On-chain | 12% |
| 6 | Exchange Netflow | On-chain | 21% |
| 7 | Funding Rate | Деривативы | 15% |
| + | RSI-BB Confluence | Overlay | ±30 |

## Зоны

| Score | Зона | Emoji |
|-------|------|-------|
| +70 to +100 | STRONG BUY | 🟢🟢 |
| +40 to +70 | ACCUMULATION | 🟢 |
| +10 to +40 | SLIGHTLY BULLISH | 🟡↑ |
| -10 to +10 | NEUTRAL | ⚪ |
| -40 to -10 | SLIGHTLY BEARISH | 🟡↓ |
| -70 to -40 | DISTRIBUTION | 🔴 |
| -100 to -70 | STRONG SELL | 🔴🔴 |

## Деплой на сервер (systemd)

```bash
sudo nano /etc/systemd/system/cryptobot.service
```

```ini
[Unit]
Description=CryptoSignal Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto-signal-bot
ExecStart=/home/ubuntu/crypto-signal-bot/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cryptobot
sudo systemctl start cryptobot
sudo systemctl status cryptobot
```

## Тесты

```bash
python tests/test_scoring.py
```

## Технические требования

- Python 3.11+
- VPS: 1 vCPU, 1 GB RAM, 10 GB SSD
- Провайдеры (РФ): Hetzner, Timeweb Cloud, VDSina

## Источники данных

- **Bybit API** (основной) — цены + funding rate (бесплатно, работает в РФ)
- **OKX API** (резервный) — fallback (бесплатно, работает в РФ)
- **CryptoQuant PRO** — on-chain метрики (платная подписка, ~$99/мес)

## ⚠️ Дисклеймер

Бот предоставляет **информационный анализ** и НЕ является финансовой рекомендацией.
Все решения о покупке/продаже принимает пользователь самостоятельно.
Бот НЕ торгует автоматически.
