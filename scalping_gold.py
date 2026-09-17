"""
scalping_gold.py — AlphaEdge 1H Swing & News Catalyst Trading Engine (Gold & DAX)
===================================================================================
HPotter UT Bot (Version 6) — Exact TradingView Pine Script Replication:
  - ATR Formula: Exact TradingView Wilder's RMA: ta.rma(tr, 10)
  - Trailing Stop: Exact f_calcTrailingStop(prev, close, nLoss)
  - Crossover Signals:
      BUY:  prev_close <= prev_stop AND current_close > current_stop
      SELL: prev_close >= prev_stop AND current_close < current_stop
  - Execution Timeframe: 1-Hour (1H)
  - Session Gateway: 08:00 AM to 08:00 PM EAT (London + New York only)
  - Target & Risk (Gold XAUUSDm, 0.01 lot):
      1. Full TP = $15.00 USD
      2. Stage 1 Break-Even Shield: Triggers at +$4.00 -> SL moves to Entry
      3. Stage 2 Profit Lock: Triggers at +$10.00 -> SL locks at +$8.00
      4. Max Initial SL Risk: $10.00 USD
  - Target & Risk (DAX DE30m, 0.10 lot):
      1. Full TP = 60 pts
      2. Stage 1 Break-Even Shield: Triggers at +25 pts -> SL moves to Entry
      3. Stage 2 Profit Lock: Triggers at +45 pts -> SL locks at +36 pts
      4. Max Initial SL Risk: 45 pts
  - News Catalyst Guidance: ForexFactory High-Impact USD & EUR live integration.
  - Instant Reversal: Closes opposite trade instantly upon verified 1H signal flip.
  - Telegram Firewall: Channel (@riffexalphaedgebot) receives entry signals & trade
    close results ONLY. All management alerts go to personal DM only.
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

# Asset Configurations (1-Hour UT Bot Swing with 2-Stage Profit Lock)
ASSET_CONFIGS = {
    "XAUUSDm": {
        "symbol": "XAUUSDm",
        "lot": 0.01,
        "key_mult": 1.0,
        "atr_period": 10,
        "tp_dollars": 15.0,              # Full Target: $15.00 USD Profit (High Probability Reach)
        "tp_catalyst_dollars": 25.0,      # Expanded $25.00 Target during News Impulse
        "be_trigger_dollars": 4.0,        # Stage 1: Move SL to Entry at $4.00 profit
        "lock_trigger_dollars": 10.0,     # Stage 2: Trigger Profit Lock at $10.00 profit
        "lock_amount_dollars": 8.0,       # Stage 2: Lock $8.00 profit into SL
        "max_sl_dollars": 10.0,           # Max Initial Risk Cap: $10.00 USD
        "sl_atr_mult": 1.2,
        "currency": "USD"
    },
    "DE30m": {
        "symbol": "DE30m",
        "lot": 0.1,                       # 0.1 Lot
        "key_mult": 1.0,
        "atr_period": 10,
        "tp_pts": 60.0,                   # Full Target: 60 pts Target
        "tp_catalyst_pts": 100.0,         # Expanded 100 pts during News Impulse
        "be_trigger_pts": 25.0,           # Stage 1: Move SL to Entry at 25 pts profit (was 15, raised to let trade breathe)
        "lock_trigger_pts": 45.0,         # Stage 2: Trigger Profit Lock at 45 pts profit
        "lock_amount_pts": 36.0,          # Stage 2: Lock 36 pts profit into SL
        "max_sl_pts": 45.0,               # Max Initial Risk Cap: 45 pts
        "sl_atr_mult": 1.2,
        "currency": "EUR"
    }
}

NEWS_ENGINE = None
ACTIVE_BE_TRACKED = {}   # ticket -> True if Stage 1 BE set
ACTIVE_LOCK_TRACKED = {} # ticket -> True if Stage 2 Lock set

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
    """Loads dynamically tuned parameters from the AI Auto-Learning Brain."""
    cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_learned_m15.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                c = json.load(f)
            # Gold: apply all tuned parameters (fallbacks match $15 TP calibration)
            ASSET_CONFIGS["XAUUSDm"]["tp_dollars"]          = float(c.get("gold_tp_dollars", 15.0))
            ASSET_CONFIGS["XAUUSDm"]["tp_catalyst_dollars"] = float(c.get("gold_tp_catalyst_dollars", 25.0))
            ASSET_CONFIGS["XAUUSDm"]["be_trigger_dollars"]  = float(c.get("gold_be_trigger_dollars", 4.0))

            # DAX: apply all tuned parameters
            ASSET_CONFIGS["DE30m"]["tp_pts"]          = float(c.get("dax_tp_pts", 60.0))
            ASSET_CONFIGS["DE30m"]["tp_catalyst_pts"] = float(c.get("dax_tp_catalyst_pts", 100.0))
            ASSET_CONFIGS["DE30m"]["be_trigger_pts"]  = float(c.get("dax_be_trigger_pts", 25.0))
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


# ─── Position Management & Break-Even Shield ──────────────────────────────────
def manage_open_positions(symbol, cfg, catalyst_state):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
        
    info = mt5.symbol_info(symbol)
    point = info.point
    contract = info.trade_contract_size
    lot = cfg['lot']
    dollar_per_point = contract * lot
    
    for pos in positions:
        ticket = pos.ticket
        entry_price = pos.price_open
        current_sl = pos.sl
        current_tp = pos.tp
        pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        current_price = pos.price_current
        
        pts_gain = (current_price - entry_price) if pos_type == "BUY" else (entry_price - current_price)
        dollar_gain = pts_gain * dollar_per_point
        
        # 1. Stage 1: Dynamic Break-Even Shield Check ($4.00 Gold / 15 pts DAX)
        is_be_active = ACTIVE_BE_TRACKED.get(ticket, False)
        if not is_be_active:
            be_condition = False
            if symbol == "XAUUSDm" and dollar_gain >= cfg['be_trigger_dollars']:
                be_condition = True
            elif symbol == "DE30m" and pts_gain >= cfg['be_trigger_pts']:
                be_condition = True
                
            if be_condition:
                new_sl = entry_price + (20 * point) if pos_type == "BUY" else entry_price - (20 * point)
                modify_sl(ticket, symbol, new_sl, current_tp)
                ACTIVE_BE_TRACKED[ticket] = True
                update_trade_be(ticket) # Record in dedicated trade analysis log
                msg = (
                    f"🛡️ <b>[Break-Even Protected]</b>\n"
                    f"Asset: <b>{symbol}</b> (#{ticket})\n"
                    f"Profit Reached: +${dollar_gain:.2f}\n"
                    f"SL moved to Entry ({entry_price:.2f}). Fakeout risk eliminated!"
                )
                logger.info(f"[{symbol}] BREAK-EVEN LOCKED on #{ticket}! Gain: ${dollar_gain:.2f}")
                _send_telegram(msg)

        # 2. Stage 2: Advanced Profit Lock ($10.00 Gold -> Lock $8.00 / 45 pts DAX -> Lock 36 pts)
        is_lock_active = ACTIVE_LOCK_TRACKED.get(ticket, False)
        if not is_lock_active:
            lock_condition = False
            if symbol == "XAUUSDm" and dollar_gain >= cfg.get('lock_trigger_dollars', 10.0):
                lock_condition = True
                lock_dist = cfg.get('lock_amount_dollars', 8.0) / dollar_per_point
            elif symbol == "DE30m" and pts_gain >= cfg.get('lock_trigger_pts', 45.0):
                lock_condition = True
                lock_dist = cfg.get('lock_amount_pts', 36.0)

            if lock_condition:
                new_sl = (entry_price + lock_dist) if pos_type == "BUY" else (entry_price - lock_dist)
                modify_sl(ticket, symbol, new_sl, current_tp)
                ACTIVE_LOCK_TRACKED[ticket] = True
                ACTIVE_BE_TRACKED[ticket] = True
                locked_profit_desc = f"+${cfg.get('lock_amount_dollars', 8.0):.2f}" if symbol == "XAUUSDm" else f"+{cfg.get('lock_amount_pts', 36.0)} pts"
                msg = (
                    f"🔒 <b>[Profit Lock Activated]</b>\n"
                    f"Asset: <b>{symbol}</b> (#{ticket})\n"
                    f"Gain Reached: +${dollar_gain:.2f}\n"
                    f"SL locked to <b>{locked_profit_desc}</b> ({new_sl:.2f}). Profit guaranteed!"
                )
                logger.info(f"[{symbol}] PROFIT LOCKED on #{ticket}! Gain: ${dollar_gain:.2f} -> SL: {new_sl:.2f}")
                _send_telegram(msg)

                
        # 3. Pre-News Profit Protection
        if catalyst_state.get('state') == 'PRE_NEWS_FREEZE' and dollar_gain > 1.0 and not is_be_active and not is_lock_active:
            new_sl = entry_price + (10 * point) if pos_type == "BUY" else entry_price - (10 * point)
            modify_sl(ticket, symbol, new_sl, current_tp)
            ACTIVE_BE_TRACKED[ticket] = True
            update_trade_be(ticket)
            msg = (
                f"⚠️ <b>[Pre-News Protection]</b>\n"
                f"Asset: <b>{symbol}</b> (#{ticket})\n"
                f"Event: <b>{catalyst_state.get('event')}</b> in {catalyst_state.get('minutes_to_release')}m\n"
                f"SL tightened to entry to protect profit before release."
            )
            logger.info(f"[{symbol}] Pre-news protection activated on #{ticket}")
            _send_telegram(msg)


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


# ─── Autonomous Scan Cycle ─────────────────────────────────────────────────────
def run_scalping_cycle():
    """
    Called autonomously every cycle from alphaedge.py.
    Monitors Gold (XAUUSDm) and DAX (DE30m) on the 15-Minute timeframe.
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

    # Check MT5 history deals to close any trades in analysis log that hit TP/SL
    try:
        sync_closed_trades_from_history()
    except Exception:
        pass

    session_ok = is_session_active()
    apply_ai_learned_settings()

    for symbol, cfg in ASSET_CONFIGS.items():
        try:
            catalyst = NEWS_ENGINE.get_market_catalyst_status(symbol)
            manage_open_positions(symbol, cfg, catalyst)
            
            ut_state = compute_m15_ut_bot(symbol, cfg['key_mult'], cfg['atr_period'])
            if not ut_state:
                continue
                
            info = mt5.symbol_info(symbol)
            contract = info.trade_contract_size
            lot = cfg['lot']
            dollar_per_pt = contract * lot
            
            # Dynamic TP based on News Catalyst state
            is_catalyst = (catalyst.get('state') == 'CATALYST_IMPULSE')
            event_name = catalyst.get('event', 'None')
            if is_catalyst:
                if symbol == "XAUUSDm":
                    tp_dist = cfg['tp_catalyst_dollars'] / dollar_per_pt
                else:
                    tp_dist = cfg['tp_catalyst_pts']
                mode_desc = f"⚡ Catalyst Impulse ({event_name})"
            else:
                if symbol == "XAUUSDm":
                    tp_dist = cfg['tp_dollars'] / dollar_per_pt
                else:
                    tp_dist = cfg['tp_pts']
                mode_desc = "Standard 1H Target"
                
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
            logger.info(
                f"[1H Swing] {symbol} | Price: {curr_price:.2f} | UT Stop: {ut_state['stop']:.2f} | "
                f"Trend: {ut_state['trend']} | Pos: {len(positions) if positions else 0} | "
                f"Session: {'OPEN' if session_ok else 'CLOSED'} | News: {catalyst.get('state')}"
            )
            
            # Signal Crossover Execution
            # Block entries during: PRE_NEWS_FREEZE (5min before) and NEWS_SPIKE_BLOCK (0-5min after)
            news_blocks_entry = catalyst.get('state') in ('PRE_NEWS_FREEZE', 'NEWS_SPIKE_BLOCK')

            if ut_state['cross_up']:
                # Fresh crossover on the last closed bar
                close_opposite_positions(symbol, "BUY")
                positions = mt5.positions_get(symbol=symbol)
                has_pos = len(positions) > 0 if positions else False
                if session_ok and not news_blocks_entry:
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        sl = tick.ask - sl_dist
                        tp = tick.ask + tp_dist
                        if execute_order(symbol, "BUY", cfg['lot'], sl, tp, mode_desc, event_name, ut_state['stop'], ut_state['atr']):
                            LAST_EXECUTED_BAR[symbol] = bar_time
                            _save_bar_state(LAST_EXECUTED_BAR)  # persist — survives restart

            elif ut_state['cross_dn']:
                # Fresh crossover on the last closed bar
                close_opposite_positions(symbol, "SELL")
                positions = mt5.positions_get(symbol=symbol)
                has_pos = len(positions) > 0 if positions else False
                if session_ok and not news_blocks_entry:
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        sl = tick.bid + sl_dist
                        tp = tick.bid - tp_dist
                        if execute_order(symbol, "SELL", cfg['lot'], sl, tp, mode_desc, event_name, ut_state['stop'], ut_state['atr']):
                            LAST_EXECUTED_BAR[symbol] = bar_time
                            _save_bar_state(LAST_EXECUTED_BAR)  # persist — survives restart

            else:
                # No fresh crossover — trend-follow entry on restart / first run mid-trend.
                # LAST_EXECUTED_BAR (persisted to disk) ensures this only fires ONCE per 1H bar,
                # even across multiple bot restarts within the same hour.
                if session_ok and not news_blocks_entry:
                    positions = mt5.positions_get(symbol=symbol)
                    has_pos = len(positions) > 0 if positions else False
                    if not has_pos and LAST_EXECUTED_BAR.get(symbol) != bar_time:
                        if ut_state['trend'] == "BUY":
                            sl = tick.ask - sl_dist
                            tp = tick.ask + tp_dist
                            logger.info(f"[1H Swing] {symbol} Trend-Follow Entry: BUY (trend active, no open position)")
                            if execute_order(symbol, "BUY", cfg['lot'], sl, tp, "1H Trend-Follow", event_name, ut_state['stop'], ut_state['atr']):
                                LAST_EXECUTED_BAR[symbol] = bar_time
                                _save_bar_state(LAST_EXECUTED_BAR)  # persist — survives restart
                        elif ut_state['trend'] == "SELL":
                            sl = tick.bid + sl_dist
                            tp = tick.bid - tp_dist
                            logger.info(f"[1H Swing] {symbol} Trend-Follow Entry: SELL (trend active, no open position)")
                            if execute_order(symbol, "SELL", cfg['lot'], sl, tp, "1H Trend-Follow", event_name, ut_state['stop'], ut_state['atr']):
                                LAST_EXECUTED_BAR[symbol] = bar_time
                                _save_bar_state(LAST_EXECUTED_BAR)  # persist — survives restart

        except Exception as e:
            logger.error(f"[1H Swing] Error processing {symbol}: {e}\n{traceback.format_exc()}")

