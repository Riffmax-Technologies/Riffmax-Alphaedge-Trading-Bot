"""
scalping_gold.py — AlphaEdge 1H Stop-and-Reverse + ATR Trailing Engine (Gold & DAX)
======================================================================================
Strategy: Stop-and-Reverse with Dynamic ATR Trailing Stop (NO hedging)
HPotter UT Bot (Version 6) — Exact TradingView Pine Script Replication:
  - ATR Formula: Exact TradingView Wilder's RMA: ta.rma(tr, 10)
  - Trailing Stop: Exact f_calcTrailingStop(prev, close, nLoss)
  - Crossover Signals:
      BUY:  prev_close <= prev_stop AND current_close > current_stop
      SELL: prev_close >= prev_stop AND current_close < current_stop
  - Execution Timeframe: 1-Hour (1H)
  - Session Gateway: 08:00 AM to 08:00 PM EAT (London + New York only)

Core Logic:
  1. On 1H BUY crossover  -> Close any SELL -> Open BUY (NO fixed TP)
  2. On 1H SELL crossover -> Close any BUY  -> Open SELL (NO fixed TP)
  3. On trend-follow (no crossover, no open position) -> Enter trend direction
  4. ATR Trailing Stop: every cycle the UT Bot stop line trails the open position
     SL upward (BUY) or downward (SELL) — locks profits bar by bar.
     Trade auto-closes when price violates the trail (MT5 SL hit).
  5. Multi-TF confirmation: M15 trend must agree with 1H direction at entry.

  - Lot Sizes: XAUUSDm 0.01 lot | DE30m 0.20 lot
  - Initial SL: 1.2x ATR from entry (capped at max_sl config)
  - TP: NONE (trade runs until opposite 1H signal OR trail is violated)
  - News Catalyst Guidance: ForexFactory High-Impact USD & EUR live integration.
  - Telegram Firewall: Channel (@riffexalphaedgebot) receives entry signals &
    trade close results ONLY. All management alerts go to personal DM only.
"""

import os
import json
import logging
import traceback
import urllib.request
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from news_catalyst_engine import NewsCatalystEngine
from m15_trade_analysis_logger import (
    log_trade_opened,
    update_trade_be,
    log_trade_closed,
    sync_closed_trades_from_history,
    get_performance_summary
)

logger = logging.getLogger("AlphaEdge.M15Swing")

# Asset Configurations — Stop-and-Reverse + ATR Trailing (NO fixed TP)
ASSET_CONFIGS = {
    "XAUUSDm": {
        "symbol": "XAUUSDm",
        "lot": 0.01,
        "key_mult": 1.0,
        "atr_period": 10,
        "max_sl_dollars": 10.0,     # Max initial SL risk: $10.00
        "sl_atr_mult": 1.2,         # Initial SL = 1.2 × ATR from entry
        "trail_min_profit_dollars": 3.0,  # Only start trailing after $3 profit (avoids whipsaws)
        "currency": "USD"
    },
    "DE30m": {
        "symbol": "DE30m",
        "lot": 0.2,                 # 0.20 lot for good per-point profit
        "key_mult": 1.0,
        "atr_period": 10,
        "max_sl_pts": 30.0,         # Max initial SL risk: 30 pts
        "sl_atr_mult": 1.2,         # Initial SL = 1.2 × ATR from entry
        "trail_min_profit_pts": 10.0,  # Only start trailing after 10 pts profit
        "currency": "EUR"
    }
}

NEWS_ENGINE = None
# Track which tickets already have ATR trailing active (in-memory)
ACTIVE_TRAILING = {}  # ticket -> True if trailing has started


# ─── Persistent Bar State (survives bot restarts — prevents re-entry on same 1H bar) ────
_BAR_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_executed_bar.json")

def _load_bar_state():
    """Load LAST_EXECUTED_BAR from disk. Returns dict of {symbol: bar_time (int)}."""
    try:
        if os.path.exists(_BAR_STATE_FILE):
            with open(_BAR_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Only keep bars from the current trading day — stale days are cleared
            now_utc = datetime.now(timezone.utc)
            today_date = now_utc.date()
            filtered = {}
            for sym, ts in data.items():
                bar_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                if bar_dt == today_date:
                    filtered[sym] = int(ts)
            return filtered
    except Exception:
        pass
    return {}

def _save_bar_state(bar_dict):
    """Persist LAST_EXECUTED_BAR to disk."""
    try:
        with open(_BAR_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(bar_dict, f)
    except Exception:
        pass

# Load on startup — populated with today's already-executed bars (if any)
LAST_EXECUTED_BAR = _load_bar_state()


def apply_ai_learned_settings():
    """Loads dynamically tuned parameters from the AI Auto-Learning Brain.
    Note: In the new SAR+ATR Trailing strategy, TP is dynamic (trail-based).
    We only carry forward lot/SL parameters if present.
    """
    cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_learned_m15.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                c = json.load(f)
            # Only apply lot/SL params; TP is now trail-based (no fixed target)
            if "gold_max_sl_dollars" in c:
                ASSET_CONFIGS["XAUUSDm"]["max_sl_dollars"] = float(c["gold_max_sl_dollars"])
            if "dax_max_sl_pts" in c:
                ASSET_CONFIGS["DE30m"]["max_sl_pts"] = float(c["dax_max_sl_pts"])
        except Exception as e:
            logger.debug(f"[Scalp] Dynamic config load skipped: {e}")


try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
except Exception:
    pass

# ─── Telegram Alerts & Strict Channel Firewall ─────────────────────────────────
_TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
_TELEGRAM_PERSONAL  = os.getenv("TELEGRAM_CHAT_ID", "915238743")              # Owner DM — receives ALL messages
_TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL_ID", "@riffexalphaedgebot") # Public channel — trade signals ONLY

def _is_channel_allowed(message: str) -> bool:
    """
    STRICT ENFORCEMENT FIREWALL FOR PUBLIC CHANNEL (@riffexalphaedgebot):
    Only two types of messages are ever permitted:
      1. Trade Entry Signals: containing [AlphaEdge Signal]
      2. Trade Exit Results: containing [Trade Closed
    All other messages (Daily Reports, Market Summaries, Bot Status, News Briefings,
    30-min countdowns, Break-Even notices, Pre-news protections, AI updates, Errors)
    are strictly dropped and NEVER sent to the channel.
    """
    msg_lower = message.lower()

    # Blocklist: any of these immediately disqualifies message from channel
    blocked_keywords = [
        "daily", "weekly", "report", "analysis", "briefing",
        "bot status", "bot offline", "bot online", "shut down", "started",
        "scanner paused", "scanner resumed", "command", "balance & pnl",
        "account equity", "break-even protected", "pre-news", "30-minute news",
        "economic calendar", "protection activated", "capital preserved", "fakeout risk"
    ]
    for kw in blocked_keywords:
        if kw in msg_lower:
            return False

    # Allowlist: must have valid trade entry or close tag
    is_entry = "[alphaedge signal]" in msg_lower
    is_close = "[trade closed" in msg_lower

    return is_entry or is_close

def _tg_send(chat_id, message):
    """Low-level: sends a single message to one recipient with strict firewall."""
    if not _TELEGRAM_TOKEN or not chat_id:
        return

    # FIREWALL CHECK: If recipient is the public channel, verify message whitelist
    if str(chat_id).strip().lower() in (_TELEGRAM_CHANNEL.lower(), "-1003973403139", "@riffexalphaedgebot"):
        if not _is_channel_allowed(message):
            logger.warning(f"[Telegram Firewall] BLOCKED non-trade message to channel: {message[:60]}...")
            return

    url = "https://api.telegram.org/bot" + _TELEGRAM_TOKEN + "/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        try:
            p2 = {"chat_id": chat_id, "text": message}
            data = json.dumps(p2).encode("utf-8")
            req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass

def _send_personal(message):
    """Sends to owner DM ONLY (915238743) — never to public channel."""
    _tg_send(_TELEGRAM_PERSONAL, message)

def _send_signal(message):
    """Sends to BOTH owner DM AND public channel (subject to strict channel firewall)."""
    _tg_send(_TELEGRAM_PERSONAL, message)
    _tg_send(_TELEGRAM_CHANNEL, message)

def send_trade_entry_broadcast(symbol, order_type, price, lot, sl, tp, catalyst_desc="Standard"):
    """Broadcasts clean trade entry signal to channel and owner DM."""
    channel_msg = (
        f"🚀 <b>[AlphaEdge Signal]</b>\n"
        f"Asset: <b>{symbol}</b>\n"
        f"Action: <b>{order_type}</b> @ {price:.2f}\n"
        f"Take Profit: {tp:.2f}\n"
        f"Stop Loss: {sl:.2f}"
    )
    dm_msg = (
        f"🚀 <b>[AlphaEdge Signal]</b>\n"
        f"Asset: <b>{symbol}</b>\n"
        f"Action: <b>{order_type}</b> @ {price:.2f}\n"
        f"Volume: {lot} Lot\n"
        f"Stop Loss: {sl:.2f}\n"
        f"Take Profit: {tp:.2f}\n"
        f"Mode: {catalyst_desc}"
    )
    _tg_send(_TELEGRAM_PERSONAL, dm_msg)
    _tg_send(_TELEGRAM_CHANNEL, channel_msg)

def send_trade_close_broadcast(symbol, direction, open_price, close_price, pnl_usd, reason):
    """Broadcasts trade result (Win/Loss) to both public channel and owner DM."""
    if pnl_usd > 0:
        emoji = "🎯"
        tag = "WIN"
        result_text = f"✅ <b>+${pnl_usd:.2f} (WIN)</b>"
        detail = "Take Profit Target Hit!" if reason == "TP_HIT" else "Closed in Profit"
    elif pnl_usd < 0:
        emoji = "🛑"
        tag = "LOSS"
        result_text = f"❌ <b>-${abs(pnl_usd):.2f} (LOSS)</b>"
        detail = "Stop Loss Executed" if reason == "SL_HIT" else "Closed with Loss"
    else:
        emoji = "🛡️"
        tag = "BREAK-EVEN"
        result_text = f"⚪ <b>${pnl_usd:+.2f} (BREAK-EVEN)</b>"
        detail = "Break-Even Capital Protected"

    if reason == "REVERSAL":
        detail = "M15 UT Bot Signal Flip Reversal"

    msg = (
        f"{emoji} <b>[Trade Closed — {tag}]</b>\n"
        f"Asset: <b>{symbol}</b> ({direction})\n"
        f"Entry: {open_price} ➔ Exit: {close_price}\n"
        f"Result: {result_text}\n"
        f"Outcome: {detail}"
    )
    _tg_send(_TELEGRAM_PERSONAL, msg)
    _tg_send(_TELEGRAM_CHANNEL, msg)

# Alias for backwards-compatibility: default to personal only
def _send_telegram(message):
    _send_personal(message)



# ─── Session Filter (London 8:00 AM EAT to New York 8:00 PM EAT) ─────────────────
def is_session_active():
    """
    Session Gateway:
    Active strictly from 08:00 AM EAT (05:00 UTC) to 08:00 PM EAT (17:00 UTC).
    Covers London Open through peak New York session.
    Entries outside this window (Asian / overnight chop) and weekends are blocked.
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    
    # EAT is UTC+3
    now_eat = now_utc + timedelta(hours=3)
    hour_eat = now_eat.hour

    # Weekend close (Friday 20:00 EAT through Sunday 20:00 EAT)
    if weekday == 4 and hour_eat >= 20:
        return False
    if weekday == 5:
        return False
    if weekday == 6 and hour_eat < 20:
        return False

    # Strictly 8:00 AM EAT to 8:00 PM EAT (08:00 <= hour < 20:00)
    return 8 <= hour_eat < 20


# ─── Exact TradingView Pine Script Replication ─────────────────────────────────
def compute_m15_ut_bot(symbol, key_mult=1.0, atr_period=10, n_bars=300):
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, n_bars)
    if rates is None or len(rates) < 50:
        return None
        
    df = pd.DataFrame(rates)
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df.apply(
        lambda r: max(
            r['high'] - r['low'],
            abs(r['high'] - r['prev_close']) if not np.isnan(r['prev_close']) else 0,
            abs(r['low']  - r['prev_close']) if not np.isnan(r['prev_close']) else 0,
        ), axis=1)

    # Exact Pine Script ta.rma(tr, atr_period)
    tr_vals = df['tr'].values
    atr_tv = np.zeros(len(df))
    atr_tv[:atr_period] = tr_vals[:atr_period].mean()
    for i in range(atr_period, len(df)):
        atr_tv[i] = (tr_vals[i] + (atr_period - 1.0) * atr_tv[i-1]) / float(atr_period)
    df['atr_tv'] = atr_tv

    # Exact Pine Script f_calcTrailingStop(prev, close, nLoss)
    closes = df['close'].values
    stops = np.zeros(len(closes))
    
    for i in range(1, len(closes)):
        nLoss = key_mult * atr_tv[i]
        prev_stop = stops[i-1]
        c_price = closes[i]
        p_price = closes[i-1]
        
        if c_price > prev_stop and p_price > prev_stop:
            stops[i] = max(prev_stop, c_price - nLoss)
        elif c_price < prev_stop and p_price < prev_stop:
            stops[i] = min(prev_stop, c_price + nLoss)
        elif c_price > prev_stop:
            stops[i] = c_price - nLoss
        else:
            stops[i] = c_price + nLoss

    # Index -2 is the latest fully confirmed/closed M15 bar
    last_closed_idx = -2
    p_close = closes[last_closed_idx - 1]
    p_stop  = stops[last_closed_idx - 1]
    c_close = closes[last_closed_idx]
    c_stop  = stops[last_closed_idx]
    c_atr   = atr_tv[last_closed_idx]
    bar_time = int(df['time'].iloc[last_closed_idx])
    
    # Exact TradingView HPotter UT Bot crossover / crossunder
    cross_up = (p_close <= p_stop) and (c_close > c_stop)
    cross_dn = (p_close >= p_stop) and (c_close < c_stop)
    current_trend = "BUY" if c_close > c_stop else "SELL"
    
    return {
        "cross_up": cross_up,
        "cross_dn": cross_dn,
        "trend": current_trend,
        "close": c_close,
        "stop": c_stop,
        "atr": c_atr,
        "bar_time": bar_time
    }


# ─── ATR Trailing Stop Position Manager ────────────────────────────────────────
def manage_open_positions(symbol, cfg, catalyst_state, ut_state=None):
    """
    Trails the SL of open positions using the live 1H UT Bot stop line.
    - For BUY: moves SL up to ut_stop whenever ut_stop > current_sl (only after min profit)
    - For SELL: moves SL down to ut_stop whenever ut_stop < current_sl (only after min profit)
    - Pre-news: if close to news event and in profit, tighten SL to near-entry to protect.
    """
    global ACTIVE_TRAILING
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    info = mt5.symbol_info(symbol)
    if not info:
        return
    contract = info.trade_contract_size
    lot = cfg['lot']
    dollar_per_pt = contract * lot
    decimals = 2 if symbol == "XAUUSDm" else 1

    # UT Bot stop line (trailing anchor)
    ut_stop = ut_state['stop'] if ut_state else None

    for pos in positions:
        ticket = pos.ticket
        entry_price = pos.price_open
        current_sl = pos.sl
        pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        current_price = pos.price_current

        pts_gain = (current_price - entry_price) if pos_type == "BUY" else (entry_price - current_price)
        dollar_gain = pts_gain * dollar_per_pt

        # ── 1. Dynamic ATR Trailing Stop ─────────────────────────────────────────
        if ut_stop is not None:
            # Check if trade has enough profit to start trailing (avoids whipsaw on first bar)
            trail_active = ACTIVE_TRAILING.get(ticket, False)
            min_profit_met = False
            if symbol == "XAUUSDm":
                min_profit_met = dollar_gain >= cfg.get("trail_min_profit_dollars", 3.0)
            elif symbol == "DE30m":
                min_profit_met = pts_gain >= cfg.get("trail_min_profit_pts", 10.0)

            if not trail_active and min_profit_met:
                ACTIVE_TRAILING[ticket] = True
                trail_active = True
                logger.info(f"[{symbol}] ATR TRAILING ACTIVATED on #{ticket} | Gain: ${dollar_gain:.2f}")
                _send_telegram(
                    f"🔄 <b>[Trailing Active]</b>\n"
                    f"Asset: <b>{symbol}</b> (#{ticket})\n"
                    f"Profit Reached: +${dollar_gain:.2f}\n"
                    f"SL now trails UT Bot stop line. Profit protected dynamically."
                )

            if trail_active:
                if pos_type == "BUY":
                    # Trail up: new SL = ut_stop, but only if it's ABOVE current SL (ratchet up)
                    if ut_stop > current_sl:
                        modify_sl(ticket, symbol, ut_stop, 0.0)
                        logger.info(
                            f"[{symbol}] TRAIL UP #{ticket}: SL {current_sl:.{decimals}f} -> {ut_stop:.{decimals}f}"
                        )
                elif pos_type == "SELL":
                    # Trail down: new SL = ut_stop, but only if it's BELOW current SL (ratchet down)
                    # For SELL, current_sl is above price; trail downward means lower value
                    if current_sl == 0.0 or ut_stop < current_sl:
                        modify_sl(ticket, symbol, ut_stop, 0.0)
                        logger.info(
                            f"[{symbol}] TRAIL DOWN #{ticket}: SL {current_sl:.{decimals}f} -> {ut_stop:.{decimals}f}"
                        )

        # ── 2. Pre-News Profit Protection ────────────────────────────────────────
        # If a high-impact news event is <5 min away and trade is in profit, tighten SL
        if catalyst_state.get('state') == 'PRE_NEWS_FREEZE' and dollar_gain > 1.5:
            # Tighten SL to 5 pts above/below entry (locks a small gain, avoids spike loss)
            tight_sl_pts = 5.0
            if pos_type == "BUY":
                tight_sl = entry_price + tight_sl_pts
                if tight_sl > current_sl:
                    modify_sl(ticket, symbol, tight_sl, 0.0)
                    logger.info(f"[{symbol}] PRE-NEWS TIGHTEN on #{ticket}: SL -> {tight_sl:.{decimals}f}")
                    _send_telegram(
                        f"⚠️ <b>[Pre-News Protection]</b>\n"
                        f"Asset: <b>{symbol}</b> (#{ticket})\n"
                        f"Event: <b>{catalyst_state.get('event')}</b> in "
                        f"{catalyst_state.get('minutes_to_release')}m\n"
                        f"SL tightened to protect +${dollar_gain:.2f} profit before release."
                    )
            else:
                tight_sl = entry_price - tight_sl_pts
                if current_sl == 0.0 or tight_sl < current_sl:
                    modify_sl(ticket, symbol, tight_sl, 0.0)
                    logger.info(f"[{symbol}] PRE-NEWS TIGHTEN on #{ticket}: SL -> {tight_sl:.{decimals}f}")
                    _send_telegram(
                        f"⚠️ <b>[Pre-News Protection]</b>\n"
                        f"Asset: <b>{symbol}</b> (#{ticket})\n"
                        f"Event: <b>{catalyst_state.get('event')}</b> in "
                        f"{catalyst_state.get('minutes_to_release')}m\n"
                        f"SL tightened to protect +${dollar_gain:.2f} profit before release."
                    )




def modify_sl(ticket, symbol, new_sl, tp):
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": round(new_sl, 2 if symbol == "XAUUSDm" else 1),
        "tp": round(tp, 2 if symbol == "XAUUSDm" else 1)
    }
    res = mt5.order_send(req)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(f"Failed to modify SL #{ticket}: {res.comment}")


def execute_order(symbol, order_type, lot, sl, tp, catalyst_desc="Standard", news_name="None", ut_stop=0.0, atr=0.0):
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if order_type == "BUY" else tick.bid
    o_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
    
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": o_type,
        "price": price,
        "sl": round(sl, 2 if symbol == "XAUUSDm" else 1),
        "tp": round(tp, 2 if symbol == "XAUUSDm" else 1),
        "deviation": 20,
        "magic": 20250831,
        "comment": "M15_UT_SWING",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[{symbol}] {order_type} EXECUTED! Ticket: #{res.order} | Price: {price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
        # Log to dedicated trade analysis CSV starting from upgrade
        log_trade_opened(
            ticket=res.order,
            symbol=symbol,
            direction=order_type,
            lot=lot,
            open_price=price,
            sl=sl,
            tp=tp,
            target_metric=catalyst_desc,
            news_catalyst=news_name,
            ut_stop=ut_stop,
            atr=atr
        )
        send_trade_entry_broadcast(
            symbol=symbol,
            order_type=order_type,
            price=price,
            lot=lot,
            sl=sl,
            tp=tp,
            catalyst_desc=catalyst_desc
        )
        return res.order
    else:
        logger.error(f"[{symbol}] Order Failed: {res.comment} (Retcode: {res.retcode})")
        return None


def close_opposite_positions(symbol, target_dir):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    info = mt5.symbol_info(symbol)
    contract = info.trade_contract_size if info else 100.0
    for pos in positions:
        pos_dir = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        if pos_dir != target_dir:
            tick = mt5.symbol_info_tick(symbol)
            c_price = tick.bid if pos_dir == "BUY" else tick.ask
            c_type = mt5.ORDER_TYPE_SELL if pos_dir == "BUY" else mt5.ORDER_TYPE_BUY
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": symbol,
                "volume": pos.volume,
                "type": c_type,
                "price": c_price,
                "deviation": 20,
                "magic": 20250831,
                "comment": "REVERSAL_CLOSE",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            pts = (c_price - pos.price_open) if pos_dir == "BUY" else (pos.price_open - c_price)
            pnl_usd = pts * contract * pos.volume
            log_trade_closed(pos.ticket, c_price, pnl_usd, "REVERSAL")
            logger.info(f"[{symbol}] REVERSAL: Closed opposite {pos_dir} #{pos.ticket} at {c_price:.2f}")
            send_trade_close_broadcast(
                symbol=symbol,
                direction=pos_dir,
                open_price=f"{pos.price_open:.2f}",
                close_price=f"{c_price:.2f}",
                pnl_usd=round(pnl_usd, 2),
                reason="REVERSAL"
            )


# ─── M15 Confirmation Helper ───────────────────────────────────────────────────
def compute_m15_trend(symbol, key_mult=1.0, atr_period=10, n_bars=100):
    """Compute UT Bot trend on M15 for entry confirmation. Returns 'BUY', 'SELL', or None."""
    try:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, n_bars)
        if rates is None or len(rates) < 20:
            return None
        df = pd.DataFrame(rates)
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = df.apply(
            lambda r: max(
                r['high'] - r['low'],
                abs(r['high'] - r['prev_close']) if not np.isnan(r['prev_close']) else 0,
                abs(r['low']  - r['prev_close']) if not np.isnan(r['prev_close']) else 0,
            ), axis=1)
        tr_vals = df['tr'].values
        atr_tv = np.zeros(len(df))
        atr_tv[:atr_period] = tr_vals[:atr_period].mean()
        for i in range(atr_period, len(df)):
            atr_tv[i] = (tr_vals[i] + (atr_period - 1.0) * atr_tv[i-1]) / float(atr_period)
        closes = df['close'].values
        stops = np.zeros(len(closes))
        for i in range(1, len(closes)):
            nLoss = key_mult * atr_tv[i]
            prev_stop = stops[i-1]
            c_price = closes[i]
            p_price = closes[i-1]
            if c_price > prev_stop and p_price > prev_stop:
                stops[i] = max(prev_stop, c_price - nLoss)
            elif c_price < prev_stop and p_price < prev_stop:
                stops[i] = min(prev_stop, c_price + nLoss)
            elif c_price > prev_stop:
                stops[i] = c_price - nLoss
            else:
                stops[i] = c_price + nLoss
        c_close = closes[-2]
        c_stop  = stops[-2]
        return "BUY" if c_close > c_stop else "SELL"
    except Exception:
        return None


# ─── Autonomous Scan Cycle ─────────────────────────────────────────────────────
def run_scalping_cycle():
    """
    Called autonomously every cycle from alphaedge.py.
    Strategy: Stop-and-Reverse + ATR Trailing Stop (NO fixed TP, NO hedging).
      - 1H crossover BUY  -> close any SELL, open BUY (no TP, trail SL)
      - 1H crossover SELL -> close any BUY,  open SELL (no TP, trail SL)
      - Trend-follow: enter on 1H trend when no position open (M15 confirmation required)
      - ATR Trail: every cycle moves SL along 1H UT Bot stop line to lock profits
    """
    global NEWS_ENGINE, LAST_EXECUTED_BAR
    if NEWS_ENGINE is None:
        NEWS_ENGINE = NewsCatalystEngine()

    try:
        NEWS_ENGINE.sync_calendar()
    except Exception:
        pass

    # Daily news briefing — fires once per day on first cycle
    try:
        NEWS_ENGINE.send_daily_briefing()
    except Exception:
        pass

    # 30-minute countdown alerts — checked every cycle, fires once per event
    try:
        NEWS_ENGINE.check_and_send_30min_alerts()
    except Exception:
        pass

    # Check MT5 history deals to close any trades in analysis log that hit SL
    try:
        sync_closed_trades_from_history()
    except Exception:
        pass

    session_ok = is_session_active()
    apply_ai_learned_settings()

    for symbol, cfg in ASSET_CONFIGS.items():
        try:
            catalyst = NEWS_ENGINE.get_market_catalyst_status(symbol)

            # ── Compute 1H UT Bot state first (needed for trailing + entries) ──
            ut_state = compute_m15_ut_bot(symbol, cfg['key_mult'], cfg['atr_period'])
            if not ut_state:
                continue

            # ── Trail SL on all open positions using live UT Bot stop ──────────
            manage_open_positions(symbol, cfg, catalyst, ut_state)

            info = mt5.symbol_info(symbol)
            contract = info.trade_contract_size
            lot = cfg['lot']
            dollar_per_pt = contract * lot

            # Initial SL distance from entry (1.2× ATR, capped at max risk)
            sl_dist = cfg['sl_atr_mult'] * ut_state['atr']
            if symbol == "XAUUSDm" and 'max_sl_dollars' in cfg:
                sl_dist = min(sl_dist, cfg['max_sl_dollars'] / dollar_per_pt)
            elif symbol == "DE30m" and 'max_sl_pts' in cfg:
                sl_dist = min(sl_dist, cfg['max_sl_pts'])

            positions = mt5.positions_get(symbol=symbol)
            has_pos = len(positions) > 0 if positions else False
            bar_time = ut_state['bar_time']

            tick = mt5.symbol_info_tick(symbol)
            curr_price = tick.bid if tick else 0.0
            event_name = catalyst.get('event', 'None')

            logger.info(
                f"[SAR] {symbol} | Price: {curr_price:.2f} | UT Stop: {ut_state['stop']:.2f} | "
                f"Trend: {ut_state['trend']} | Cross↑: {ut_state['cross_up']} Cross↓: {ut_state['cross_dn']} | "
                f"Pos: {len(positions) if positions else 0} | "
                f"Session: {'OPEN' if session_ok else 'CLOSED'} | News: {catalyst.get('state')}"
            )

            # Block new entries during PRE_NEWS_FREEZE and NEWS_SPIKE_BLOCK
            news_blocks_entry = catalyst.get('state') in ('PRE_NEWS_FREEZE', 'NEWS_SPIKE_BLOCK')

            # ── Case 1: 1H BUY Crossover (Stop-and-Reverse to BUY) ────────────
            if ut_state['cross_up']:
                # Always close any opposing SELL on crossover — no M15 filter needed here
                close_opposite_positions(symbol, "BUY")
                positions = mt5.positions_get(symbol=symbol)
                has_pos = len(positions) > 0 if positions else False

                if session_ok and not news_blocks_entry:
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        sl = tick.ask - sl_dist
                        # NO fixed TP — trail-based exit; tp=0 means no fixed TP in MT5
                        logger.info(f"[SAR] {symbol} CROSSOVER BUY -> SL: {sl:.2f} | No TP (trail)")
                        if execute_order(symbol, "BUY", cfg['lot'], sl, 0.0,
                                         "SAR Crossover BUY", event_name,
                                         ut_state['stop'], ut_state['atr']):
                            LAST_EXECUTED_BAR[symbol] = bar_time
                            _save_bar_state(LAST_EXECUTED_BAR)

            # ── Case 2: 1H SELL Crossover (Stop-and-Reverse to SELL) ──────────
            elif ut_state['cross_dn']:
                # Always close any opposing BUY on crossover — no M15 filter needed here
                close_opposite_positions(symbol, "SELL")
                positions = mt5.positions_get(symbol=symbol)
                has_pos = len(positions) > 0 if positions else False

                if session_ok and not news_blocks_entry:
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        sl = tick.bid + sl_dist
                        # NO fixed TP — trail-based exit; tp=0 means no fixed TP in MT5
                        logger.info(f"[SAR] {symbol} CROSSOVER SELL -> SL: {sl:.2f} | No TP (trail)")
                        if execute_order(symbol, "SELL", cfg['lot'], sl, 0.0,
                                         "SAR Crossover SELL", event_name,
                                         ut_state['stop'], ut_state['atr']):
                            LAST_EXECUTED_BAR[symbol] = bar_time
                            _save_bar_state(LAST_EXECUTED_BAR)

            # ── Case 3: Trend-Follow — no crossover but trend active, no position ──
            # M15 must AGREE with 1H trend to avoid entering against momentum.
            # This guard is critical — was the main failure mode (bot buying during sell).
            else:
                if session_ok and not news_blocks_entry:
                    positions = mt5.positions_get(symbol=symbol)
                    has_pos = len(positions) > 0 if positions else False
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        # M15 confirmation: direction must match 1H
                        m15_trend = compute_m15_trend(symbol, cfg['key_mult'], cfg['atr_period'])
                        trend_1h = ut_state['trend']

                        if m15_trend and m15_trend != trend_1h:
                            logger.info(
                                f"[SAR] {symbol} Trend-Follow SKIPPED: 1H={trend_1h} but M15={m15_trend} (misaligned)"
                            )
                        elif trend_1h == "BUY":
                            sl = tick.ask - sl_dist
                            logger.info(f"[SAR] {symbol} Trend-Follow BUY | M15={m15_trend} ✓ | SL: {sl:.2f}")
                            if execute_order(symbol, "BUY", cfg['lot'], sl, 0.0,
                                             "1H Trend-Follow BUY", event_name,
                                             ut_state['stop'], ut_state['atr']):
                                LAST_EXECUTED_BAR[symbol] = bar_time
                                _save_bar_state(LAST_EXECUTED_BAR)
                        elif trend_1h == "SELL":
                            sl = tick.bid + sl_dist
                            logger.info(f"[SAR] {symbol} Trend-Follow SELL | M15={m15_trend} ✓ | SL: {sl:.2f}")
                            if execute_order(symbol, "SELL", cfg['lot'], sl, 0.0,
                                             "1H Trend-Follow SELL", event_name,
                                             ut_state['stop'], ut_state['atr']):
                                LAST_EXECUTED_BAR[symbol] = bar_time
                                _save_bar_state(LAST_EXECUTED_BAR)

        except Exception as e:
            logger.error(f"[SAR] Error processing {symbol}: {e}\n{traceback.format_exc()}")

