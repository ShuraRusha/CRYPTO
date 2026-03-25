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

def _forecast(score):
    if score >= 70: return "ПРОГНОЗ (1-3 нед): Высокая вероятность роста. Зона набора позиции."
    if score >= 40: return "ПРОГНОЗ (1-2 нед): Умеренно позитивно. Можно присматриваться."
    if score >= 10: return "ПРОГНОЗ (1-2 нед): Слабый бычий сигнал. Выжидательная позиция."
    if score >= -10: return "ПРОГНОЗ: Нет направления. Ждать сигнала."
    if score >= -40: return "ПРОГНОЗ (1-2 нед): Давление продавцов. Осторожность."
    if score >= -70: return "ПРОГНОЗ (1-3 нед): Рынок перегрет. Риск коррекции."
    return "ПРОГНОЗ: Сильный сигнал на продажу. Фиксация прибыли."

def _calc_groups(result):
    w = result.get("effective_weights", {"rsi": 0.13, "macd": 0.09, "bollinger": 0.08, "mvrv": 0.22, "sopr": 0.12, "exchange_flow": 0.21, "funding_rate": 0.15})
    rsi_s = result.get("rsi", {}).get("total", result.get("rsi", {}).get("score", 0))
    macd_s = result.get("macd", {}).get("score", 0)
    bb_s = result.get("bb", {}).get("score", 0)
    tech = rsi_s * w.get("rsi", 0) + macd_s * w.get("macd", 0) + bb_s * w.get("bollinger", 0)
    mvrv_s = result.get("mvrv", {}).get("score", 0) if result.get("mvrv") else 0
    sopr_s = result.get("sopr", {}).get("score", 0) if result.get("sopr") else 0
    exch_s = result.get("exchange_flow", {}).get("score", 0) if result.get("exchange_flow") else 0
    onchain = mvrv_s * w.get("mvrv", 0) + sopr_s * w.get("sopr", 0) + exch_s * w.get("exchange_flow", 0)
    fund_s = result.get("funding", {}).get("score", 0) if result.get("funding") else 0
    deriv = fund_s * w.get("funding_rate", 0)
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
    mvrv = result.get("mvrv")
    sopr = result.get("sopr")
    exch = result.get("exchange_flow")
    funding = result.get("funding")
    confluence = result.get("confluence_flag", "")
    conf_bonus = result.get("confluence_bonus", 0)
    missing = result.get("missing_indicators", [])
    tech_pts, onchain_pts, deriv_pts = _calc_groups(result)
    L = []
    L.append(f"{zone['emoji']} <b>{zone['name']}</b> -- {coin}/USDT {trend}")
    L.append(f"<b>${price:,.2f}</b> | Score: <b>{score:+.0f}</b>/100")
    L.append("")
    L.append(f"<b>--- Техника ({tech_pts:+.0f} очков) ---</b>")
    rsi_val = rsi.get("total", rsi.get("score", 0))
    L.append(f"RSI: {rsi_val:+.0f}")
    L.append(f"  <i>{_hint_rsi(rsi_val)}</i>")
    if rsi.get("divergence_label"):
        L.append(f"  {rsi['divergence_label']} ({rsi['divergence_bonus']:+d})")
    mi = "Бычий кросс" if macd.get("cross_up") else "Медвежий кросс" if macd.get("cross_down") else "Hist +" if macd.get("histogram_score", 0) > 0 else "Hist -"
    L.append(f"MACD: {macd.get('score', 0):+.0f}  ({mi})")
    L.append(f"  <i>{_hint_macd(mi)}</i>")
    pctb = bb.get("percent_b", 0.5)
    L.append(f"BB: {bb.get('score', 0):+.0f}  (%B={pctb:.2f})")
    L.append(f"  <i>{_hint_bb(pctb)}</i>")
    if bb.get("squeeze"):
        L.append("  SQUEEZE -- жди резкое движение!")
    if confluence:
        L.append("")
        L.append("<b>--- RSI+BB ---</b>")
        L.append(f"{confluence} ({conf_bonus:+d})")
    L.append("")
    L.append(f"<b>--- On-chain ({onchain_pts:+.0f} очков) ---</b>")
    if mvrv:
        L.append(f"MVRV: {mvrv['score']:+.0f}")
        L.append(f"  <i>{_hint_mvrv(mvrv['score'])}</i>")
    elif "mvrv" in missing:
        L.append("MVRV: нет данных")
    if sopr:
        L.append(f"SOPR: {sopr['score']:+.0f}  (SMA7={sopr['sopr_sma']:.4f})")
        L.append(f"  <i>{_hint_sopr(sopr['sopr_sma'])}</i>")
    elif "sopr" in missing:
        L.append("SOPR: нет данных")
    if exch:
        dr = "отток" if exch["netflow_24h"] < 0 else "приток"
        L.append(f"Биржи: {exch['score']:+.0f}  ({dr} {abs(exch['netflow_24h']):,.0f}/24ч)")
        L.append(f"  <i>{_hint_exch(exch['netflow_24h'])}</i>")
    elif "exchange_flow" in missing:
        L.append("Биржи: нет данных")
    L.append("")
    L.append(f"<b>--- Деривативы ({deriv_pts:+.0f} очков) ---</b>")
    if funding:
        L.append(f"Funding: {funding['score']:+.0f}  ({funding['avg_funding_pct']:.4f}%)")
        L.append(f"  <i>{_hint_funding(funding['score'])}</i>")
    elif "funding_rate" in missing:
        L.append("Funding: нет данных")
    if missing:
        L.append(f"\nНедоступно: {', '.join(missing)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"\n{now}")
    L.append(f"\n<b>{_forecast(score)}</b>")
    L.append("\nNFA/DYOR")
    return "\n".join(L)

def format_scan_table(results, previous_results=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    previous_results = previous_results or {}
    L = [f"<b>MARKET SCAN</b> {now}", ""]
    sorted_r = sorted(results, key=lambda x: x["composite_score"], reverse=True)
    for i, r in enumerate(sorted_r, 1):
        z = classify_zone(r["composite_score"])
        p = previous_results.get(r["coin"])
        t = get_trend_arrow(r["composite_score"], p.get("composite_score") if p else None)
        rsi_s = r.get("rsi", {}).get("total", r.get("rsi", {}).get("score", 0))
        macd_s = r.get("macd", {}).get("score", 0)
        bb_s = r.get("bb", {}).get("score", 0)
        mvrv_s = r.get("mvrv", {}).get("score", "—") if r.get("mvrv") else "—"
        sopr_s = r.get("sopr", {}).get("score", "—") if r.get("sopr") else "—"
        exch_s = r.get("exchange_flow", {}).get("score", "—") if r.get("exchange_flow") else "—"
        fund_s = r.get("funding", {}).get("score", "—") if r.get("funding") else "—"
        mvrv_t = f"{mvrv_s:+.0f}" if isinstance(mvrv_s, (int, float)) else mvrv_s
        sopr_t = f"{sopr_s:+.0f}" if isinstance(sopr_s, (int, float)) else sopr_s
        exch_t = f"{exch_s:+.0f}" if isinstance(exch_s, (int, float)) else exch_s
        fund_t = f"{fund_s:+.0f}" if isinstance(fund_s, (int, float)) else fund_s
        tech, onchain, deriv = _calc_groups(r)
        L.append(f"{i}. {z['emoji']} <b>{r['coin']}</b> {r['composite_score']:+.0f} {t}")
        L.append(f"   Тех({tech:+.0f}): RSI {rsi_s:+.0f} | MACD {macd_s:+.0f} | BB {bb_s:+.0f}")
        L.append(f"   Он({onchain:+.0f}): MVRV {mvrv_t} | SOPR {sopr_t} | Бирж {exch_t}")
        L.append(f"   Дер({deriv:+.0f}): Fund {fund_t}")
        L.append("")
    sb = [r for r in sorted_r if r["composite_score"] >= 70]
    ss = [r for r in sorted_r if r["composite_score"] <= -70]
    if sb: L.append(f"Покупка: {', '.join(r['coin'] for r in sb)}")
    if ss: L.append(f"Продажа: {', '.join(r['coin'] for r in ss)}")
    if not sb and not ss: L.append("Сильных сигналов нет.")
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
    L = [f"<b>DAILY DIGEST</b> {now}"]
    ch = []
    for r in results:
        p = previous_results.get(r["coin"])
        if p:
            d = r["composite_score"] - p["composite_score"]
            if abs(d) >= 3: ch.append((r["coin"], r["composite_score"], d))
    if ch:
        ch.sort(key=lambda x: abs(x[2]), reverse=True)
        L.append("")
        L.append("<b>24ч:</b>")
        for c, s, d in ch[:8]: L.append(f"  {c}: {s:+.0f} ({d:+.0f})")
    best = max(results, key=lambda x: x["composite_score"])
    L.append(f"\n<b>{_forecast(best['composite_score'])}</b>")
    L.append("\n/scan")
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
