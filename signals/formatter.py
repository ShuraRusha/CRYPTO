from datetime import datetime, timezone
from signals.classifier import classify_zone, get_trend_arrow
from typing import Optional

def _hint_rsi(val):
    if val <= 0: return "Рынок в панике, монета перепродана"
    if val >= 50: return "Рынок в эйфории, монета перекуплена"
    if val > 0: return "Слабый бычий импульс"
    return "Слабое медвежье давление"

def _hint_macd(info):
    if "Бычий" in info: return "Тренд разворачивается вверх"
    if "Медвежий" in info: return "Тренд разворачивается вниз"
    if "+" in info: return "Бычий импульс усиливается"
    return "Медвежий импульс усиливается"

def _hint_bb(pctb):
    if pctb < 0.2: return "Цена у дна канала - дешево"
    if pctb > 0.8: return "Цена у потолка - дорого"
    if pctb < 0.5: return "Цена в нижней половине канала"
    return "Цена в верхней половине канала"

def _hint_mvrv(score):
    if score > 50: return "Холдеры в убытке - зона накопления"
    if score > 0: return "Холдеры около безубытка"
    if score > -50: return "Холдеры в прибыли - осторожность"
    return "Холдеры в большой прибыли - риск фиксации"

def _hint_sopr(sma):
    if sma < 0.97: return "Капитуляция - продают в убыток"
    if sma < 1.0: return "Продают около безубытка"
    if sma < 1.05: return "Умеренная фиксация прибыли"
    return "Массовая фиксация прибыли - давление продавцов"

def _hint_exch(nf):
    if nf < 0: return "Монеты уходят с бирж - не планируют продавать"
    return "Монеты поступают на биржи - готовятся продавать"

def _hint_funding(score):
    if score > 30: return "Шорты перегружены - шорт-сквиз вероятен"
    if score > 0: return "Умеренный медвежий перекос на фьючерсах"
    if score > -30: return "Умеренный бычий перекос на фьючерсах"
    return "Лонги перегружены - риск ликвидаций"

def _hint_fear_greed(value):
    if value <= 25: return f"Экстремальный страх ({value}) — зона покупки"
    if value <= 45: return f"Страх ({value}) — осторожный интерес"
    if value <= 55: return f"Нейтральный сентимент ({value})"
    if value <= 75: return f"Жадность ({value}) — осторожность"
    return f"Экстремальная жадность ({value}) — риск коррекции"

def _forecast(score):
    if score >= 70: return "ПРОГНОЗ (1-3 нед): Высокая вероятность роста. Зона набора позиции."
    if score >= 40: return "ПРОГНОЗ (1-2 нед): Умеренно позитивно. Можно присматриваться."
    if score >= 10: return "ПРОГНОЗ (1-2 нед): Слабый бычий сигнал. Выжидательная позиция."
    if score >= -10: return "ПРОГНОЗ: Нет направления. Ждать сигнала."
    if score >= -40: return "ПРОГНОЗ (1-2 нед): Давление продавцов. Осторожность."
    if score >= -70: return "ПРОГНОЗ (1-3 нед): Рынок перегрет. Риск коррекции."
    return "ПРОГНОЗ: Сильный сигнал на продажу. Фиксация прибыли."

def _calc_groups(result):
    w = result.get("effective_weights", {
        "rsi": 0.10, "macd": 0.08, "bollinger": 0.07, "ema": 0.08, "stoch_rsi": 0.05,
        "obv": 0.05, "mvrv": 0.16, "sopr": 0.09, "exchange_flow": 0.15,
        "funding_rate": 0.12, "fear_greed": 0.05,
    })
    rsi_s = result.get("rsi", {}).get("total", result.get("rsi", {}).get("score", 0))
    macd_s = result.get("macd", {}).get("score", 0)
    bb_s = result.get("bb", {}).get("score", 0)
    ema_s = result.get("ema", {}).get("score", 0) if result.get("ema") else 0
    stoch_s = result.get("stoch_rsi", {}).get("score", 0) if result.get("stoch_rsi") else 0
    tech = (rsi_s * w.get("rsi", 0) + macd_s * w.get("macd", 0) + bb_s * w.get("bollinger", 0)
            + ema_s * w.get("ema", 0) + stoch_s * w.get("stoch_rsi", 0))
    obv_s = result.get("obv", {}).get("score", 0) if result.get("obv") else 0
    mvrv_s = result.get("mvrv", {}).get("score", 0) if result.get("mvrv") else 0
    sopr_s = result.get("sopr", {}).get("score", 0) if result.get("sopr") else 0
    exch_s = result.get("exchange_flow", {}).get("score", 0) if result.get("exchange_flow") else 0
    onchain = (mvrv_s * w.get("mvrv", 0) + sopr_s * w.get("sopr", 0)
               + exch_s * w.get("exchange_flow", 0) + obv_s * w.get("obv", 0))
    fund_s = result.get("funding", {}).get("score", 0) if result.get("funding") else 0
    fg_s = result.get("fear_greed", {}).get("score", 0) if result.get("fear_greed") else 0
    deriv = fund_s * w.get("funding_rate", 0) + fg_s * w.get("fear_greed", 0)
    return tech, onchain, deriv

def format_coin_detail(result, previous_result=None):
    coin = result["coin"]
    score = result["composite_score"]
    price = result["price"]
    zone = classify_zone(score)
    trend = get_trend_arrow(score, previous_result.get("composite_score") if previous_result else None)
    rsi = result.get("rsi", {})
    macd = result.get("macd", {})
    bb = result.get("bb", {})
    ema = result.get("ema")
    stoch = result.get("stoch_rsi")
    obv = result.get("obv")
    adx = result.get("adx")
    mvrv = result.get("mvrv")
    sopr = result.get("sopr")
    exch = result.get("exchange_flow")
    funding = result.get("funding")
    fear_greed = result.get("fear_greed")
    confluence = result.get("confluence_flag", "")
    conf_bonus = result.get("confluence_bonus", 0)
    adx_mult = result.get("adx_multiplier", 1.0)
    tech_pts, onchain_pts, deriv_pts = _calc_groups(result)

    L = []
    L.append(f"{zone['emoji']} <b>{zone['name']}</b> — {coin}/USDT {trend}")
    L.append(f"<b>${price:,.2f}</b>  |  Score: <b>{score:+.0f}</b>/100")

    # ADX note
    if adx is not None:
        adx_note = "сильный тренд" if adx >= 30 else "умеренный тренд" if adx >= 20 else "боковик — сигналы слабее"
        L.append(f"<i>ADX {adx:.0f} — {adx_note}</i>")

    # --- Техника ---
    L.append("")
    L.append(f"<b>📈 Техника ({tech_pts:+.0f} очков)</b>")

    rsi_val = rsi.get("total", rsi.get("score", 0))
    L.append(f"RSI: {rsi_val:+.0f}  —  <i>{_hint_rsi(rsi_val)}</i>")
    if rsi.get("divergence_label"):
        L.append(f"  ↳ {rsi['divergence_label']} ({rsi['divergence_bonus']:+d})")

    mi = "Бычий кросс" if macd.get("cross_up") else "Медвежий кросс" if macd.get("cross_down") else "Hist +" if macd.get("histogram_score", 0) > 0 else "Hist -"
    L.append(f"MACD: {macd.get('score', 0):+.0f}  —  <i>{_hint_macd(mi)}</i>")

    pctb = bb.get("percent_b", 0.5)
    L.append(f"BB: {bb.get('score', 0):+.0f}  (%B={pctb:.2f})  —  <i>{_hint_bb(pctb)}</i>")
    if bb.get("squeeze"):
        L.append("  ⚡ SQUEEZE — жди резкого движения!")

    if ema:
        L.append(f"EMA 50/200: {ema['score']:+.0f}  —  <i>{ema['regime']}</i>")
        if ema.get("golden_cross"):
            L.append("  ⭐ Золотой кросс!")
        elif ema.get("death_cross"):
            L.append("  ☠️ Мёртвый кросс!")

    if stoch:
        L.append(f"StochRSI: {stoch['score']:+.0f}  (K={stoch['k']:.0f})  —  <i>{stoch['signal']}</i>")

    if obv:
        L.append(f"OBV: {obv['score']:+.0f}  —  <i>{obv['signal']}</i>")

    if confluence:
        L.append(f"RSI+BB: <i>{confluence}</i> ({conf_bonus:+d})")

    # --- On-chain ---
    has_onchain = any([mvrv, sopr, exch])
    if has_onchain:
        L.append("")
        L.append(f"<b>⛓ On-chain ({onchain_pts:+.0f} очков)</b>")
        if mvrv:
            L.append(f"MVRV: {mvrv['score']:+.0f}  —  <i>{_hint_mvrv(mvrv['score'])}</i>")
        if sopr:
            L.append(f"SOPR: {sopr['score']:+.0f}  (SMA7={sopr['sopr_sma']:.4f})  —  <i>{_hint_sopr(sopr['sopr_sma'])}</i>")
        if exch:
            dr = "отток" if exch["netflow_24h"] < 0 else "приток"
            L.append(f"Биржи: {exch['score']:+.0f}  ({dr} {abs(exch['netflow_24h']):,.0f}/24ч)  —  <i>{_hint_exch(exch['netflow_24h'])}</i>")

    # --- Деривативы ---
    L.append("")
    L.append(f"<b>💹 Деривативы ({deriv_pts:+.0f} очков)</b>")
    if funding:
        L.append(f"Funding: {funding['score']:+.0f}  ({funding['avg_funding_pct']:.4f}%)  —  <i>{_hint_funding(funding['score'])}</i>")

    # --- Сентимент ---
    if fear_greed:
        L.append("")
        L.append("<b>🌡 Сентимент рынка</b>")
        L.append(f"Fear & Greed: {fear_greed['score']:+.0f}  —  <i>{_hint_fear_greed(fear_greed['value'])}</i>")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"\n{now}")
    L.append(f"\n<b>{_forecast(score)}</b>")
    L.append("\n<i>NFA/DYOR</i>")
    return "\n".join(L)

def _fmt_price(price):
    if price >= 10000:
        return f"${price/1000:.1f}K"
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:.2f}"
    return f"${price:.4f}"

def _scan_hint(r):
    """One plain-language sentence — always returned for every coin."""
    score = r["composite_score"]

    # Confluence is always top priority
    if r.get("confluence_flag"):
        return r["confluence_flag"]

    hints = []

    # Technical signals
    rsi = r.get("rsi", {})
    bb = r.get("bb", {})
    macd = r.get("macd", {})
    rsi_val = rsi.get("total", rsi.get("score", 0))

    if macd.get("cross_up"):
        hints.append("Бычий кросс MACD")
    elif macd.get("cross_down"):
        hints.append("Медвежий кросс MACD")
    if rsi.get("divergence_label"):
        hints.append(rsi["divergence_label"])
    if bb.get("squeeze"):
        hints.append("BB Squeeze — жди резкого движения")
    if abs(rsi_val) >= 20:
        hints.append(_hint_rsi(rsi_val))
    pctb = bb.get("percent_b", 0.5)
    if pctb < 0.2 or pctb > 0.8:
        hints.append(_hint_bb(pctb))

    # On-chain signals
    exch = r.get("exchange_flow")
    mvrv = r.get("mvrv")
    sopr = r.get("sopr")
    if exch and abs(exch["score"]) >= 20:
        hints.append(_hint_exch(exch["netflow_24h"]))
    if mvrv and abs(mvrv["score"]) >= 20:
        hints.append(_hint_mvrv(mvrv["score"]))
    if sopr and abs(sopr["score"]) >= 20:
        hints.append(_hint_sopr(sopr["sopr_sma"]))

    # Funding
    funding = r.get("funding")
    if funding and abs(funding["score"]) >= 20:
        hints.append(_hint_funding(funding["score"]))

    # EMA cross signals (high priority)
    ema = r.get("ema")
    if ema:
        if ema.get("golden_cross"):
            hints.insert(0, "Золотой кросс EMA — сильный бычий сигнал")
        elif ema.get("death_cross"):
            hints.insert(0, "Мёртвый кросс EMA — сильный медвежий сигнал")

    # StochRSI extreme signals
    stoch = r.get("stoch_rsi")
    if stoch and abs(stoch.get("score", 0)) >= 50:
        hints.append(stoch["signal"])

    # OBV divergence
    obv = r.get("obv")
    if obv and "дивергенция" in obv.get("signal", "").lower():
        hints.append(obv["signal"])

    # Fear & Greed extreme
    fg = r.get("fear_greed")
    if fg and abs(fg.get("score", 0)) >= 60:
        hints.append(_hint_fear_greed(fg["value"]))

    if hints:
        return hints[0]

    # Fallback — describe the neutral/weak state
    if score >= 10:
        return "Слабый бычий сигнал, выжидательная позиция"
    if score <= -10:
        return "Слабое медвежье давление, осторожность"
    return "Нейтральный рынок, нет явного направления"

def format_scan_table(results, previous_results=None):
    now = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")
    previous_results = previous_results or {}
    sorted_r = sorted(results, key=lambda x: x["composite_score"], reverse=True)

    bullish = sum(1 for r in results if r["composite_score"] >= 10)
    bearish = sum(1 for r in results if r["composite_score"] <= -10)
    neutral = len(results) - bullish - bearish

    L = [
        f"📊 <b>MARKET SCAN</b>",
        f"<i>{now}</i>",
        f"🟢 {bullish} бычьих  ·  ⚪ {neutral} нейтр.  ·  🔴 {bearish} медвежьих",
        "",
    ]

    for r in sorted_r:
        z = classify_zone(r["composite_score"])
        p = previous_results.get(r["coin"])
        t = get_trend_arrow(r["composite_score"], p.get("composite_score") if p else None)
        tech, onchain, deriv = _calc_groups(r)
        price_str = _fmt_price(r["price"])
        has_onchain = any([r.get("mvrv"), r.get("sopr"), r.get("exchange_flow")])

        # Line 1: zone emoji + coin + score + trend + price
        L.append(f"{z['emoji']} <b>{r['coin']}</b>  {r['composite_score']:+.0f} {t}  <i>{price_str}</i>")

        # Line 2: group scores
        if has_onchain:
            L.append(f"   📈 {tech:+.0f}  ·  ⛓ {onchain:+.0f}  ·  💹 {deriv:+.0f}")
        else:
            L.append(f"   📈 {tech:+.0f}  ·  💹 {deriv:+.0f}")

        # Line 3: plain language hint
        hint = _scan_hint(r)
        if hint:
            L.append(f"   <i>{hint}</i>")

        L.append("")

    # Summary
    sb = [r for r in sorted_r if r["composite_score"] >= 70]
    ss = [r for r in sorted_r if r["composite_score"] <= -70]
    if sb or ss:
        L.append("⚡ <b>СИГНАЛЫ</b>")
        if sb:
            L.append(f"   🟢 Купить:   {', '.join(r['coin'] for r in sb)}")
        if ss:
            L.append(f"   🔴 Продать:  {', '.join(r['coin'] for r in ss)}")
    else:
        L.append("Сильных сигналов нет.")

    best = max(sorted_r, key=lambda x: x["composite_score"])
    L.append(f"\n<b>{_forecast(best['composite_score'])}</b>")
    return "\n".join(L)

def format_top(results):
    s = sorted(results, key=lambda x: x["composite_score"], reverse=True)
    L = ["<b>ТОП-3 покупка:</b>"]
    for i, r in enumerate(s[:3], 1):
        z = classify_zone(r["composite_score"])
        L.append(f"  {i}. {z['emoji']} {r['coin']} {r['composite_score']:+.0f}")
    L.append("")
    L.append("<b>ТОП-3 продажа:</b>")
    for i, r in enumerate(s[-3:][::-1], 1):
        z = classify_zone(r["composite_score"])
        L.append(f"  {i}. {z['emoji']} {r['coin']} {r['composite_score']:+.0f}")
    L.append(f"\n<b>{_forecast(s[0]['composite_score'])}</b>")
    return "\n".join(L)

def format_daily_digest(results, previous_results=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    previous_results = previous_results or {}
    sorted_r = sorted(results, key=lambda x: x["composite_score"], reverse=True)

    bullish = [r for r in results if r["composite_score"] >= 10]
    bearish = [r for r in results if r["composite_score"] <= -10]
    neutral = [r for r in results if -10 < r["composite_score"] < 10]

    L = [f"\U0001f4ca <b>DAILY DIGEST</b> \u2014 {now}", ""]

    # Market overview
    L.append("\U0001f30d <b>ОБЗОР РЫНКА</b>")
    L.append(f"Монет: {len(results)}  \U0001f7e2 Бычьих: {len(bullish)}  \u26aa Нейтральных: {len(neutral)}  \U0001f534 Медвежьих: {len(bearish)}")

    # Top 3 bullish
    L.append("")
    L.append("\U0001f4c8 <b>ТОП ПОКУПКА</b>")
    for i, r in enumerate(sorted_r[:3], 1):
        z = classify_zone(r["composite_score"])
        p = previous_results.get(r["coin"])
        t = get_trend_arrow(r["composite_score"], p.get("composite_score") if p else None)
        L.append(f"  {i}. {z['emoji']} <b>{r['coin']}</b> {r['composite_score']:+.0f} {t}")

    # Top 3 bearish
    L.append("")
    L.append("\U0001f4c9 <b>ТОП ПРОДАЖА</b>")
    bottom3 = sorted_r[-3:][::-1]
    for i, r in enumerate(bottom3, 1):
        z = classify_zone(r["composite_score"])
        p = previous_results.get(r["coin"])
        t = get_trend_arrow(r["composite_score"], p.get("composite_score") if p else None)
        L.append(f"  {i}. {z['emoji']} <b>{r['coin']}</b> {r['composite_score']:+.0f} {t}")

    # 24h changes
    ch = []
    for r in results:
        p = previous_results.get(r["coin"])
        if p:
            d = r["composite_score"] - p["composite_score"]
            if abs(d) >= 5:
                ch.append((r["coin"], r["composite_score"], d))
    if ch:
        ch.sort(key=lambda x: abs(x[2]), reverse=True)
        L.append("")
        L.append("\U0001f504 <b>ИЗМЕНЕНИЯ ЗА 24Ч</b>")
        for c, s, d in ch[:6]:
            arrow = "\u2191" if d > 0 else "\u2193"
            L.append(f"  {arrow} <b>{c}</b>: {s:+.0f} ({d:+.0f})")

    # Strong signals
    strong_buy = [r for r in sorted_r if r["composite_score"] >= 70]
    strong_sell = [r for r in sorted_r if r["composite_score"] <= -70]
    if strong_buy or strong_sell:
        L.append("")
        L.append("\u26a1 <b>СИЛЬНЫЕ СИГНАЛЫ</b>")
        if strong_buy:
            L.append(f"  \U0001f7e2 Купить: {', '.join(r['coin'] for r in strong_buy)}")
        if strong_sell:
            L.append(f"  \U0001f534 Продать: {', '.join(r['coin'] for r in strong_sell)}")

    best = sorted_r[0]
    L.append("")
    L.append(f"<b>{_forecast(best['composite_score'])}</b>")
    L.append("")
    L.append("/scan \u2014 полный анализ  |  /coin BTC \u2014 детально")
    L.append("\n<i>NFA/DYOR</i>")
    return "\n".join(L)

def format_alert(alert, result):
    L = []
    L.append(f"<b>ALERT</b> [{alert['priority']}]")
    L.append(alert["message"])
    L.append(f"Score: {result['composite_score']:+.0f} | ${result['price']:,.2f}")
    L.append(f"\n<b>{_forecast(result['composite_score'])}</b>")
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    L.append(f"{now}")
    return "\n".join(L)
