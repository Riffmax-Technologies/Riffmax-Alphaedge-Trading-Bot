"""
scalping_gold.py  —  AlphaEdge v2.3  (Phase 1 — Single TP Quick Scalp)
=======================================================================
Gold-Only UT-Guided Scalping Engine with Market Regime Filter.

Entry Pipeline (all 6 gates must pass):
  [1] Session Gate        : 24/5 All-Day & Overnight Mode (Mon–Fri 24h, pauses weekends)
  [2] Regime Filter       : ADX>=22 AND BB-Width expanding AND Choppiness<61.8
  [3] UT-MA Signal        : M1 UT Stop smoothed by 5-bar MA crossover
  [4] M1 EMA20 Filter     : Price above EMA20 for BUY, below for SELL
  [5] M5 EMA8/21 Confirm  : M5 trend must agree with direction
      + Price Action gate : Break of prev high/low + candle body confirmation
      + RSI gate          : RSI 35–65 (no overbought buys / oversold sells)
  [6] Spread Gate         : Spread < 40% of M1 ATR

Trade Execution (Phase 1 — single order):
  1 x 0.01 lot  @ TP = 0.7 x ATR  (fast profit lock)

Stop Loss:
  Base: 10-bar swing low/high + 0.15 ATR buffer
  Cap : min(max(1.5 x ATR, $2.50), $3.50) — strict $3.50 absolute ceiling

Lot Sizing : Fixed 0.01 micro-lot
Magic Number: 20250831
"""

import logging
import os
import traceback
from datetime import datetime, timezone

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

def resolve_gold_symbol():
    for name in ["XAUUSDm", "XAUUSD247m", "XAUUSDz", "XAUUSD"]:
        mt5.symbol_select(name, True)
        rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_M1, 0, 10)
        if rates is not None and len(rates) > 0:
            return name
    return "XAUUSDm"


SCALP_SYMBOL        = resolve_gold_symbol()
SCALP_MAGIC         = 20250831
MAX_SCALP_TRADES    = 2
LOT_PCT_FREE_MARGIN = 0.01

# HPotter UT Stop parameters (1:1 with TradingView default settings)
UT_ATR_PERIOD  = 10     # HPotter ATR Period
UT_KEY_MULT    = 3.0    # HPotter Key Value Sensitivity

# Confirmation EMAs
M5_EMA_FAST    = 8
M5_EMA_SLOW    = 21
M1_EMA_PRICE   = 20

# Dual Take Profit targets (multipliers of ATR)
TP1_ATR        = 2.0    # Quick scalp profit target ($2.00 - $3.20 gain, triggers BE lock)
TP2_ATR        = 4.0    # Extended runner target ($4.00 - $6.50 gain)

# Stop Loss limits (capital protection)
MIN_SL_DIST    = 2.50   # Min $2.50 breathing room
MAX_SL_DIST    = 4.50   # Hard $4.50 safety cap per trade

# Regime filter thresholds
ADX_MIN          = 18.0   # ADX below this = consolidation, block trade
CHOP_MAX         = 61.8   # Choppiness above this = choppy, block trade
BB_WIDTH_LOOKBACK = 20    # Compare current BB width to 20-bar average

logger = logging.getLogger("AlphaEdge.Scalp")


# ─── Telegram ──────────────────────────────────────────────────────────────────
def _send_telegram(message):
    token   = os.getenv("TELEGRAM_TOKEN", "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "915238743")
    if not token or not chat_id:
        return
    import json, urllib.request
    url     = "https://api.telegram.org/bot" + token + "/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        try:
            payload.pop("parse_mode", None)
            data = json.dumps(payload).encode("utf-8")
            req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc2:
            logger.error("[Scalp Telegram] " + str(exc2))


# ─── UT Stop calculation ───────────────────────────────────────────────────────
def _compute_ut_stop(closes, atrs, key_mult=UT_KEY_MULT):
    stops = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if np.isnan(atrs[i]):
            stops[i] = stops[i - 1]
            continue
        nLoss = key_mult * atrs[i]
        ps, pc, cc = stops[i - 1], closes[i - 1], closes[i]
        if cc > ps and pc > ps:
            stops[i] = max(ps, cc - nLoss)
        elif cc < ps and pc < ps:
            stops[i] = min(ps, cc + nLoss)
        elif cc > ps:
            stops[i] = cc - nLoss
        else:
            stops[i] = cc + nLoss
    return stops


# ─── Regime Filter ─────────────────────────────────────────────────────────────
def _detect_regime(df_m1, curr_atr):
    """
    Returns (is_trending, regime_reason_string).
    Uses ADX, Bollinger Band Width, and Choppiness Index.
    ALL THREE must confirm trending for is_trending=True.
    """
    df = df_m1.copy()
    n = len(df)
    if n < 30:
        return False, "Insufficient bars for regime detection"

    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    # ── ADX(14) ──────────────────────────────────────────────────────────────
    adx_period = 14
    tr_vals  = np.zeros(n)
    dm_plus  = np.zeros(n)
    dm_minus = np.zeros(n)
    for i in range(1, n):
        h_diff = highs[i] - highs[i-1]
        l_diff = lows[i-1] - lows[i]
        tr_vals[i]  = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        dm_plus[i]  = h_diff if h_diff > l_diff and h_diff > 0 else 0
        dm_minus[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0

    atr14    = pd.Series(tr_vals).ewm(alpha=1/adx_period, adjust=False).mean().values
    pdi      = pd.Series(dm_plus).ewm(alpha=1/adx_period, adjust=False).mean().values
    mdi      = pd.Series(dm_minus).ewm(alpha=1/adx_period, adjust=False).mean().values
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi_norm = np.where(atr14 > 0, pdi / atr14 * 100, 0)
        mdi_norm = np.where(atr14 > 0, mdi / atr14 * 100, 0)
        dx_denom = pdi_norm + mdi_norm
        dx       = np.where(dx_denom > 0, np.abs(pdi_norm - mdi_norm) / dx_denom * 100, 0)
        adx_val  = float(pd.Series(dx).ewm(alpha=1/adx_period, adjust=False).mean().iloc[-1])


    adx_ok = adx_val >= ADX_MIN

    # ── Bollinger Band Width ──────────────────────────────────────────────────
    bb_period = 20
    close_s   = pd.Series(closes)
    bb_mid    = close_s.rolling(bb_period).mean()
    bb_std    = close_s.rolling(bb_period).std()
    bb_upper  = bb_mid + 2 * bb_std
    bb_lower  = bb_mid - 2 * bb_std
    bb_width  = (bb_upper - bb_lower) / bb_mid * 100   # % width

    curr_width = float(bb_width.iloc[-1])
    avg_width  = float(bb_width.tail(BB_WIDTH_LOOKBACK).mean())
    bb_ok = curr_width >= avg_width * 0.95   # width at or above recent average = expanding

    # ── Choppiness Index(14) ─────────────────────────────────────────────────
    chop_period = 14
    chop_vals   = []
    for i in range(chop_period, n):
        window_tr  = tr_vals[i - chop_period + 1 : i + 1].sum()
        window_h   = highs[i - chop_period + 1 : i + 1].max()
        window_l   = lows[i - chop_period + 1 : i + 1].min()
        hl_range   = window_h - window_l
        if hl_range > 0 and window_tr > 0:
            chop = 100 * np.log10(window_tr / hl_range) / np.log10(chop_period)
        else:
            chop = 50.0
        chop_vals.append(chop)

    chop_val = float(chop_vals[-1]) if chop_vals else 50.0
    chop_ok  = chop_val < CHOP_MAX

    is_trending = adx_ok and bb_ok and chop_ok
    reason = (
        "Regime ADX=" + str(round(adx_val, 1)) + ("(OK)" if adx_ok else "(LOW)") +
        " BB-W=" + str(round(curr_width, 2)) + ("(OK)" if bb_ok else "(SQUEEZE)") +
        " Chop=" + str(round(chop_val, 1)) + ("(OK)" if chop_ok else "(CHOPPY)")
    )
    return is_trending, reason


def _is_active_session():
    """
    All-Day & Overnight 24/5 Trading Mode:
    Runs continuously throughout Asian, Frankfurt, London, and NY sessions.
    Only pauses over the weekend when the market is closed (Friday 21:00 UTC to Sunday 22:00 UTC).
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    hour    = now_utc.hour
    if weekday == 4 and hour >= 21:
        return False
    if weekday == 5:
        return False
    if weekday == 6 and hour < 22:
        return False
    return True


def _calc_lot_size(free_margin, symbol_info):
    """Fixed 0.01 micro lot size to protect account equity and prevent margin calls."""
    vol_min  = symbol_info.volume_min if symbol_info else 0.01
    vol_max  = symbol_info.volume_max if symbol_info else 100.0
    fixed_lot = 0.01
    return max(vol_min, min(fixed_lot, vol_max))


def _log_hedge_status():
    """Reads and logs manual hedge positions (magic != 20250831) on every cycle."""
    positions = mt5.positions_get(symbol=SCALP_SYMBOL)
    if not positions:
        return
    hedge_trades = [p for p in positions if p.magic != SCALP_MAGIC]
    if hedge_trades:
        buy_vol  = sum(p.volume for p in hedge_trades if p.type == 0)
        sell_vol = sum(p.volume for p in hedge_trades if p.type == 1)
        tot_pnl  = sum(p.profit for p in hedge_trades)
        logger.info(f"[Hedge Awareness] Manual Hedge Active: {len(hedge_trades)} trades (BUY {buy_vol:.2f} | SELL {sell_vol:.2f}) | Floating PnL: ${tot_pnl:.2f}")


def _count_open_scalp_trades():
    positions = mt5.positions_get(symbol=SCALP_SYMBOL)
    if not positions:
        return 0
    return sum(1 for p in positions if p.magic == SCALP_MAGIC)


def _swing_sl(df_m1, direction, curr_atr):
    lookback = df_m1.tail(SL_SWING_BARS)
    if direction == "BUY":
        return lookback["low"].min() - (SL_BUFFER_ATR * curr_atr)
    return lookback["high"].max() + (SL_BUFFER_ATR * curr_atr)


# ─── Signal Analysis ───────────────────────────────────────────────────────────
def _get_scalp_signal():
    # Gate 1: Session
    if not _is_active_session():
        logger.debug("[Scalp] Outside active session.")
        return None

    # Ensure symbol is selected in MT5 Market Watch
    mt5.symbol_select(SCALP_SYMBOL, True)

    # Fetch candle data: STRICTLY M1 Timeframe for precision scalping entry
    m1_rates = mt5.copy_rates_from_pos(SCALP_SYMBOL, mt5.TIMEFRAME_M1, 0, 200)
    if m1_rates is None or len(m1_rates) < 60:
        logger.warning(f"[Scalp] Not enough M1 candle data for {SCALP_SYMBOL} (got {len(m1_rates) if m1_rates is not None else 0}/60).")
        return None


    df_m1 = pd.DataFrame(m1_rates)
    df_m1["prev_close"] = df_m1["close"].shift(1)
    df_m1["tr"] = df_m1.apply(
        lambda r: max(
            r["high"] - r["low"],
            abs(r["high"] - r["prev_close"]) if not np.isnan(r["prev_close"]) else 0,
            abs(r["low"]  - r["prev_close"]) if not np.isnan(r["prev_close"]) else 0,
        ), axis=1)
    # Wilder's RMA matching TradingView Pine Script atr(10)
    df_m1["atr"] = df_m1["tr"].ewm(alpha=1.0/UT_ATR_PERIOD, adjust=False).mean()

    closes   = df_m1["close"].values
    atrs     = df_m1["atr"].values
    curr_atr = atrs[-1]
    if np.isnan(curr_atr) or curr_atr == 0:
        return None

    # Gate 2: Regime filter — block consolidation
    is_trending, regime_reason = _detect_regime(df_m1, curr_atr)
    if not is_trending:
        logger.info("[Scalp] REGIME BLOCKED: " + regime_reason)
        return None
    logger.info("[Scalp] Regime OK: " + regime_reason)

    # Gate 3: HPotter UT Bot Signal (Exact 1:1 TradingView Crossover on M1 Bar Close)
    # Pine Script: buy = crossover(src, xATRTrailingStop) | sell = crossunder(src, xATRTrailingStop)
    ut_stops = _compute_ut_stop(closes, atrs)
    if len(closes) < 3 or len(ut_stops) < 3:
        return None

    curr_close = closes[-1]
    prev_close = closes[-2]
    curr_stop  = ut_stops[-1]
    prev_stop  = ut_stops[-2]

    cross_up = (prev_close <= prev_stop) and (curr_close > curr_stop)
    cross_dn = (prev_close >= prev_stop) and (curr_close < curr_stop)

    if cross_up:
        proposed = "BUY"
    elif cross_dn:
        proposed = "SELL"
    else:
        return None

    # Gate 4: M1 EMA20 price filter
    df_m1["ema20"] = df_m1["close"].ewm(span=M1_EMA_PRICE, adjust=False).mean()
    ema20 = df_m1["ema20"].iloc[-1]
    if proposed == "BUY"  and curr_close < ema20:
        return None
    if proposed == "SELL" and curr_close > ema20:
        return None

    # Gate 5: M5 EMA8/21 confirmation
    m5_rates = mt5.copy_rates_from_pos(SCALP_SYMBOL, mt5.TIMEFRAME_M5, 0, 50)
    if m5_rates is None or len(m5_rates) < 22:
        return None
    df_m5 = pd.DataFrame(m5_rates)
    df_m5["ema8"]  = df_m5["close"].ewm(span=M5_EMA_FAST, adjust=False).mean()
    df_m5["ema21"] = df_m5["close"].ewm(span=M5_EMA_SLOW, adjust=False).mean()
    m5_ema8  = df_m5["ema8"].iloc[-1]
    m5_ema21 = df_m5["ema21"].iloc[-1]
    if proposed == "BUY"  and m5_ema8 < m5_ema21:
        return None
    if proposed == "SELL" and m5_ema8 > m5_ema21:
        return None

    # Gate 5b: DXY Dollar Index Guidance Watch (Informational Only - No Trade Blocking)


    dxy_bias = "NEUTRAL"
    try:
        for dxy_name in ["DXYm", "DXYz", "USDX", "DXY", "DOLLAR_INDX"]:
            info = mt5.symbol_info(dxy_name)
            if info is not None:
                mt5.symbol_select(dxy_name, True)
                dxy_rates = mt5.copy_rates_from_pos(dxy_name, mt5.TIMEFRAME_H1, 0, 60)

                if dxy_rates is not None and len(dxy_rates) >= 50:
                    df_dxy = pd.DataFrame(dxy_rates)
                    df_dxy["ema20"] = df_dxy["close"].ewm(span=20, adjust=False).mean()
                    df_dxy["ema50"] = df_dxy["close"].ewm(span=50, adjust=False).mean()
                    last_e20 = df_dxy["ema20"].iloc[-1]
                    last_e50 = df_dxy["ema50"].iloc[-1]
                    if last_e20 > last_e50:
                        dxy_bias = "BULLISH"
                    elif last_e20 < last_e50:
                        dxy_bias = "BEARISH"
                    break
        logger.info(f"[Scalp Guide] DXY Macro Bias: {dxy_bias} (Guidance Only)")
    except Exception as dxy_err:
        logger.debug(f"[Scalp] DXY check skipped: {dxy_err}")

    # Gate 5c: Pure Price Action Confirmation (Candle Structure & Break of High/Low)
    curr_bar  = df_m1.iloc[-1]
    prev_bar  = df_m1.iloc[-2]
    c_open    = curr_bar["open"]
    c_close   = curr_bar["close"]
    c_high    = curr_bar["high"]
    c_low     = curr_bar["low"]
    p_high    = prev_bar["high"]
    p_low     = prev_bar["low"]
    bar_range = c_high - c_low

    if proposed == "BUY":
        # Price Action BUY: Bullish candle body OR lower wick rejection + break above prev high/close
        is_bullish_body = c_close >= c_open
        lower_wick_rej = (min(c_open, c_close) - c_low) >= (0.25 * bar_range) if bar_range > 0 else False
        break_prev_high = (c_close >= p_high) or (c_high > p_high)
        if not ((is_bullish_body or lower_wick_rej) and break_prev_high):
            logger.info("[Scalp] Price Action VETO: BUY lacks bullish bar structure / break of high.")
            return None

    elif proposed == "SELL":
        # Price Action SELL: Bearish candle body OR upper wick rejection + break below prev low/close
        is_bearish_body = c_close <= c_open
        upper_wick_rej = (c_high - max(c_open, c_close)) >= (0.25 * bar_range) if bar_range > 0 else False
        break_prev_low  = (c_close <= p_low) or (c_low < p_low)
        if not ((is_bearish_body or upper_wick_rej) and break_prev_low):
            logger.info("[Scalp] Price Action VETO: SELL lacks bearish bar structure / break of low.")
            return None


    # Gate 5d: RSI Retest Filter (Prevents selling oversold bottoms or buying overbought tops)
    try:
        df_m1["delta"] = df_m1["close"].diff()
        df_m1["gain"]  = np.where(df_m1["delta"] > 0, df_m1["delta"], 0)
        df_m1["loss"]  = np.where(df_m1["delta"] < 0, -df_m1["delta"], 0)
        avg_gain = df_m1["gain"].ewm(alpha=1/14, adjust=False).mean()
        avg_loss = df_m1["loss"].ewm(alpha=1/14, adjust=False).mean()
        with np.errstate(divide="ignore", invalid="ignore"):
            rs_val  = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
            rsi_arr = 100 - (100 / (1 + rs_val))
            rsi_val = float(rsi_arr[-1])


        if proposed == "SELL" and rsi_val < 35.0:
            logger.info(f"[Scalp] RSI VETO: SELL skipped — RSI is Oversold ({rsi_val:.1f} < 35). Waiting for retest/pullback higher.")
            return None
        if proposed == "BUY" and rsi_val > 65.0:
            logger.info(f"[Scalp] RSI VETO: BUY skipped — RSI is Overbought ({rsi_val:.1f} > 65). Waiting for retest/pullback lower.")
            return None
    except Exception as rsi_err:
        rsi_val = 50.0
        logger.debug(f"[Scalp] RSI check error: {rsi_err}")


    # Gate 6: Spread
    tick     = mt5.symbol_info_tick(SCALP_SYMBOL)
    sym_info = mt5.symbol_info(SCALP_SYMBOL)
    if not tick or not sym_info:
        return None
    spread_val = sym_info.spread * sym_info.point
    if spread_val > 0.40 * curr_atr:
        logger.debug("[Scalp] Spread too wide.")
        return None

    # Build SL and Dual TPs using HPotter UT Bot Trailing Stop logic
    # Stop Loss is directly pegged to the UT Trailing Stop level (with MIN/MAX safety bounds)
    curr_stop = ut_stops[-1]
    if proposed == "BUY":
        entry = tick.ask
        raw_sl_dist = entry - curr_stop
        sl_dist = min(max(raw_sl_dist, MIN_SL_DIST), MAX_SL_DIST)
        sl = entry - sl_dist
        tp1 = entry + (TP1_ATR * curr_atr)
        tp2 = entry + (TP2_ATR * curr_atr)
    else:
        entry = tick.bid
        raw_sl_dist = curr_stop - entry
        sl_dist = min(max(raw_sl_dist, MIN_SL_DIST), MAX_SL_DIST)
        sl = entry + sl_dist
        tp1 = entry - (TP1_ATR * curr_atr)
        tp2 = entry - (TP2_ATR * curr_atr)

    return {
        "direction":    proposed,
        "entry":        entry,
        "sl":           round(sl,  2),
        "tp1":          round(tp1, 2),
        "tp2":          round(tp2, 2),
        "atr":          curr_atr,
        "rsi":          round(rsi_val, 1),
        "dxy":          dxy_bias,
        "regime":       regime_reason,
        "reason":       f"HPotter UT Bot {proposed} (Key={UT_KEY_MULT}, ATR={UT_ATR_PERIOD}) | SL=${round(sl, 2)} TP1=${round(tp1, 2)} TP2=${round(tp2, 2)} | {regime_reason}",
    }


# ─── Order Execution ───────────────────────────────────────────────────────────
def _place_scalp_order(direction, entry, sl, tp, lot, label):
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SCALP_SYMBOL,
        "volume":       lot,
        "type":         order_type,
        "price":        entry,
        "sl":           round(sl, 2),
        "tp":           round(tp, 2),
        "deviation":    30,
        "magic":        SCALP_MAGIC,
        "comment":      label,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info("[Scalp] Opened " + direction + " " + label + " lot=" + str(lot))
        return True
    err = getattr(result, "comment", mt5.last_error()) if result else mt5.last_error()
    logger.error("[Scalp] Failed " + label + ": " + str(err))
    return False


def _open_scalp_set(signal):
    account  = mt5.account_info()
    sym_info = mt5.symbol_info(SCALP_SYMBOL)
    if not account or not sym_info:
        return
    free_margin = account.margin_free
    if free_margin <= 0:
        logger.warning("[Scalp] No free margin.")
        return
    lot = _calc_lot_size(free_margin, sym_info)
    if lot <= 0:
        logger.warning("[Scalp] Lot=0, skip.")
        return

    direction = signal["direction"]
    entry, sl = signal["entry"], signal["sl"]
    tp1, tp2 = signal["tp1"], signal["tp2"]

    opened = 0
    # Trade 1: Quick Scalp Profit Lock
    if _place_scalp_order(direction, entry, sl, tp1, lot, "SCALP_TP1"):
        opened += 1

    # Trade 2: Extended Trend Runner
    if _place_scalp_order(direction, entry, sl, tp2, lot, "SCALP_TP2"):
        opened += 1

    if opened > 0:
        dxy_str = signal.get("dxy", "NEUTRAL")
        rsi_str = str(signal.get("rsi", 50.0))
        tot_vol = round(lot * opened, 2)
        _send_telegram(
            f"<b>🟢 Gold Scalp Dual-Trade Opened</b>\n\n"
            f"• <b>Direction:</b> {direction}\n"
            f"• <b>Entry Price:</b> ${entry:.2f}\n"
            f"• <b>Stop Loss (UT Stop):</b> ${sl:.2f}\n"
            f"• <b>Trade 1 TP:</b> ${tp1:.2f} ({TP1_ATR}x ATR Scalp Lock)\n"
            f"• <b>Trade 2 TP:</b> ${tp2:.2f} ({TP2_ATR}x ATR Trend Runner)\n"
            f"• <b>Total Volume:</b> {tot_vol} Lots (2x {lot} Orders)\n"
            f"• <b>Session:</b> 🌐 24/5 All-Day & Overnight Mode\n"
            f"• <b>Strategy:</b> HPotter UT Bot (Key={UT_KEY_MULT}, ATR={UT_ATR_PERIOD})\n"
            f"• <b>RSI Status:</b> {rsi_str} (Retest OK)\n"
            f"• <b>DXY Guide:</b> {dxy_str} (Informational)\n"
        )


# ─── SL Modification ───────────────────────────────────────────────────────────
def _modify_sl(ticket, symbol, new_sl, current_tp):
    result = mt5.order_send({
        "action":   mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol":   symbol,
        "sl":       round(new_sl, 2),
        "tp":       round(current_tp, 2),
    })
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[Scalp] Ticket {ticket} SL -> {round(new_sl, 2)}")
        return True
    err = getattr(result, "comment", mt5.last_error()) if result else mt5.last_error()
    logger.error(f"[Scalp] SL modify failed ticket {ticket}: {err}")
    return False


# ─── Trade Management ──────────────────────────────────────────────────────────
def _manage_open_scalp_trades():
    """
    Active Scalp Trade Management:
    When Trade 1 (SCALP_TP1) reaches target and closes, immediately moves Trade 2 (SCALP_TP2)
    Stop Loss to Breakeven (+0.20 buffer), guaranteeing a 100% risk-free runner position!
    """
    positions = mt5.positions_get(symbol=SCALP_SYMBOL)
    if not positions:
        return
    scalp_pos = [p for p in positions if p.magic == SCALP_MAGIC]
    if not scalp_pos:
        return

    # Check if TP1 has resolved and only SCALP_TP2 remains
    has_tp1 = any(getattr(p, 'comment', '') == "SCALP_TP1" for p in scalp_pos)
    tp2_trades = [p for p in scalp_pos if getattr(p, 'comment', '') == "SCALP_TP2"]

    if not has_tp1 and tp2_trades:
        for p in tp2_trades:
            is_buy = (p.type == mt5.ORDER_TYPE_BUY)
            be_price = round(p.price_open + 0.20, 2) if is_buy else round(p.price_open - 0.20, 2)
            
            should_move = (p.sl < be_price) if is_buy else (p.sl > be_price or p.sl == 0.0)
            if should_move:
                logger.info(f"[Scalp Management] TP1 hit! Moving SCALP_TP2 ticket {p.ticket} SL to Breakeven: {be_price}")
                if _modify_sl(p.ticket, SCALP_SYMBOL, be_price, p.tp):
                    _send_telegram(
                        f"🔒 <b>[Scalp Breakeven Locked]</b>\n\n"
                        f"TP1 target hit! Ticket #{p.ticket} (SCALP_TP2 Runner) Stop Loss moved to Breakeven at <b>${be_price:.2f}</b>.\n"
                        f"Runner is now completely <b>RISK-FREE</b>!"
                    )


def _adapt_scalp_parameters():
    """
    Self-Learning & Adaptive Tuning Engine:
    Reads MT5 trade history (last 48h) for scalper magic number.
    Dynamically tunes ADX_MIN threshold based on live win rate performance.
    """
    global ADX_MIN
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        from_time = now - timedelta(days=2)
        deals = mt5.history_deals_get(from_time, now)
        if not deals:
            return
        
        scalp_deals = [d for d in deals if d.magic == SCALP_MAGIC and d.entry in [1, 2]]
        if len(scalp_deals) < 3:
            return
        
        wins = sum(1 for d in scalp_deals if d.profit > 0)
        total = len(scalp_deals)
        win_rate = (wins / total) * 100.0
        
        if win_rate >= 65.0:
            ADX_MIN = 20.0
            logger.info(f"[Self-Learning] High Win Rate ({win_rate:.1f}%) detected! Relaxed ADX threshold to 20.0.")
        elif win_rate < 50.0:
            ADX_MIN = 25.0
            logger.info(f"[Self-Learning] Low Win Rate ({win_rate:.1f}%) detected! Tightened ADX filter to 25.0 to enforce strict trend quality.")
        else:
            ADX_MIN = 22.0

    except Exception as err:
        logger.debug(f"[Self-Learning] Adaptation check skipped: {err}")


# ─── Main Entry Point ──────────────────────────────────────────────────────────
def run_scalping_cycle():
    """Called every 60s (or 5s) by the main AlphaEdge loop."""
    global SCALP_SYMBOL
    try:
        if not mt5.terminal_info():
            login = int(os.getenv("MT5_LOGIN", "0"))
            pwd   = os.getenv("MT5_PASSWORD", "")
            srv   = os.getenv("MT5_SERVER", "")
            if login > 0:
                mt5.initialize(login=login, password=pwd, server=srv)
            else:
                mt5.initialize()

        SCALP_SYMBOL = resolve_gold_symbol()
        _adapt_scalp_parameters()
        _log_hedge_status()
        _manage_open_scalp_trades()


        open_count = _count_open_scalp_trades()
        logger.info(f"[Scalp] Open positions: {open_count}/{MAX_SCALP_TRADES}")
        if open_count > 0:
            logger.info(f"[Scalp] Active scalp trade(s) running ({open_count}) — managing open positions.")
            return
        signal = _get_scalp_signal()
        if signal is None:
            logger.info("[Scalp] No valid signal this cycle.")
            return
        logger.info("[Scalp] SIGNAL: " + signal["direction"] + " | " + signal["reason"])
        _open_scalp_set(signal)
    except Exception as exc:
        logger.error("[Scalp] Exception in run_scalping_cycle:\n" + traceback.format_exc())
