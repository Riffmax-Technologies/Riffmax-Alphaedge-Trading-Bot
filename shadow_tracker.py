"""
shadow_tracker.py
=================
Shadow Tracking Engine ("Paper Observation Mode")
Monitors secondary assets (EURUSDm, USOILm, US30m) without placing live MT5 orders.
Simulates theoretical entries, SL/TP execution, break-even, and profit locks.
Feeds virtual performance data into the AI Learning Engine and Telegram daily reports.
100% isolated from Gold (XAUUSDm) live execution.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import MetaTrader5 as mt5

from institutional_engine import InstitutionalEngine

logger = logging.getLogger("AlphaEdge.ShadowTracker")

# ─── Shadow Asset Configurations (Matched to Gold Option B Risk: $36 SL / $60 TP) ─
SHADOW_CONFIGS = {
    "EURUSDm": {
        "symbol": "EURUSDm",
        "name": "EUR/USD",
        "lot": 0.10,                     # 0.10 Lot ($1.00 per pip / $10,000 per full pt)
        "tp_dollars": 60.0,              # Target: $60.00 USD Profit (60 pips = 0.00600)
        "max_sl_dollars": 36.0,          # Risk Cap: $36.00 USD (36 pips = 0.00360)
        "be_trigger_dollars": 20.0,      # BE at +$20.00 (20 pips)
        "lock_trigger_dollars": 35.0,    # Trigger lock at +$35.00 (35 pips)
        "lock_amount_dollars": 25.0,     # Lock +$25.00 profit into SL (25 pips)
        "pip_size": 0.00010
    },
    "USOILm": {
        "symbol": "USOILm",
        "name": "Crude Oil (WTI)",
        "lot": 0.05,                     # 0.05 Lot ($50.00 per $1.00 move)
        "tp_dollars": 60.0,              # Target: $60.00 USD Profit ($1.20 move)
        "max_sl_dollars": 36.0,          # Risk Cap: $36.00 USD ($0.72 move)
        "be_trigger_dollars": 20.0,      # BE at +$20.00 ($0.40 move)
        "lock_trigger_dollars": 35.0,    # Trigger lock at +$35.00 ($0.70 move)
        "lock_amount_dollars": 25.0,     # Lock +$25.00 profit into SL ($0.50 move)
        "pip_size": 0.01
    },
    "US30m": {
        "symbol": "US30m",
        "name": "Dow Jones (US30)",
        "lot": 0.25,                     # 0.25 Lot ($0.25 per index point)
        "tp_dollars": 60.0,              # Target: $60.00 USD Profit (240 index pts)
        "max_sl_dollars": 36.0,          # Risk Cap: $36.00 USD (144 index pts)
        "be_trigger_dollars": 20.0,      # BE at +$20.00 (80 index pts)
        "lock_trigger_dollars": 35.0,    # Trigger lock at +$35.00 (140 index pts)
        "lock_amount_dollars": 25.0,     # Lock +$25.00 profit into SL (100 index pts)
        "pip_size": 1.0
    }
}

STATE_FILE = Path(__file__).parent / "shadow_portfolio_state.json"
HISTORY_FILE = Path(__file__).parent / "shadow_trade_history.json"

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = InstitutionalEngine()
    return _engine

def get_shadow_dollar_per_pt(symbol, lot):
    """Computes dollar value of 1.0 point for shadow symbol."""
    info = mt5.symbol_info(symbol)
    if info is None or info.trade_tick_size == 0:
        return 1.0
    return (info.trade_tick_value / info.trade_tick_size) * lot

def load_shadow_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_shadow_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save shadow state: {e}")

def load_shadow_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_shadow_history(history):
    try:
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save shadow history: {e}")

def is_shadow_session_active():
    """8:00 AM to 8:00 PM EAT (Monday to Friday) matching live trading window."""
    now_utc = datetime.now(timezone.utc)
    now_eat = now_utc + timedelta(hours=3)
    if now_eat.weekday() in (5, 6):
        return False
    if now_eat.hour < 8 or now_eat.hour >= 20:
        return False
    return True

def manage_shadow_positions():
    """Checks live prices against open shadow positions for virtual TP/SL/BE."""
    state = load_shadow_state()
    if not state:
        return

    history = load_shadow_history()
    symbols_to_delete = []

    for symbol, pos in state.items():
        cfg = SHADOW_CONFIGS.get(symbol)
        if not cfg:
            continue

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue

        curr_price = tick.bid if pos['direction'] == 'BUY' else tick.ask
        entry_price = pos['entry_price']
        dollar_per_pt = pos.get('dollar_per_pt', 1.0)
        direction = pos['direction']

        # Calculate floating PnL
        if direction == 'BUY':
            pts_pnl = curr_price - entry_price
        else:
            pts_pnl = entry_price - curr_price
        floating_usd = pts_pnl * dollar_per_pt

        # Update high-water mark
        if floating_usd > pos.get('max_profit_usd', 0.0):
            pos['max_profit_usd'] = floating_usd

        max_profit = pos.get('max_profit_usd', 0.0)

        # ── 1. Break-Even Check (+ $20.00) ───────────────────────────────────
        be_dist = (cfg['be_trigger_dollars'] / dollar_per_pt) if dollar_per_pt > 0 else 1.0
        if max_profit >= cfg['be_trigger_dollars'] and not pos.get('be_applied', False):
            pos['be_applied'] = True
            if direction == 'BUY':
                pos['current_sl'] = entry_price + (be_dist * 0.05)
            else:
                pos['current_sl'] = entry_price - (be_dist * 0.05)
            logger.info(f"[Shadow] [Shadow {symbol}] Break-Even Triggered at +${floating_usd:.2f}! SL moved to entry.")

        # ── 2. Profit Lock Check (+$35.00 -> Lock $25.00) ────────────────────
        lock_dist = (cfg['lock_amount_dollars'] / dollar_per_pt) if dollar_per_pt > 0 else 1.0
        if max_profit >= cfg['lock_trigger_dollars'] and not pos.get('lock_applied', False):
            pos['lock_applied'] = True
            if direction == 'BUY':
                pos['current_sl'] = entry_price + lock_dist
            else:
                pos['current_sl'] = entry_price - lock_dist
            logger.info(f"[Shadow] [Shadow {symbol}] Profit Lock Triggered at +${floating_usd:.2f}! Locked +${cfg['lock_amount_dollars']:.2f}.")

        # ── 3. Check Exits (TP / SL) ──────────────────────────────────────────
        closed = False
        outcome = None
        exit_price = curr_price

        if direction == 'BUY':
            if curr_price >= pos['tp_price']:
                closed = True
                outcome = "WIN_FULL_TP"
                exit_price = pos['tp_price']
            elif curr_price <= pos['current_sl']:
                closed = True
                outcome = "WIN_LOCK" if pos.get('lock_applied') else ("BE" if pos.get('be_applied') else "LOSS_SL")
                exit_price = pos['current_sl']
        else: # SELL
            if curr_price <= pos['tp_price']:
                closed = True
                outcome = "WIN_FULL_TP"
                exit_price = pos['tp_price']
            elif curr_price >= pos['current_sl']:
                closed = True
                outcome = "WIN_LOCK" if pos.get('lock_applied') else ("BE" if pos.get('be_applied') else "LOSS_SL")
                exit_price = pos['current_sl']

        if closed:
            realized_pts = (exit_price - entry_price) if direction == 'BUY' else (entry_price - exit_price)
            realized_usd = round(realized_pts * dollar_per_pt, 2)

            record = {
                "symbol": symbol,
                "name": cfg['name'],
                "direction": direction,
                "lot": pos['lot'],
                "entry_time": pos['entry_time'],
                "exit_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "realized_usd": realized_usd,
                "outcome": outcome,
                "trigger": pos.get('trigger', 'M15 UT Swing')
            }
            history.append(record)
            symbols_to_delete.append(symbol)
            logger.info(f"[Shadow] [Shadow Trade Closed] {symbol} {direction} | Result: {outcome} (${realized_usd:+.2f} USD)")

    for sym in symbols_to_delete:
        del state[sym]

    save_shadow_state(state)
    if symbols_to_delete:
        save_shadow_history(history)

def run_shadow_cycle():
    """Main observation scan loop executed alongside the master bot cycle."""
    try:
        manage_shadow_positions()

        if not is_shadow_session_active():
            return

        state = load_shadow_state()
        engine = get_engine()

        for symbol, cfg in SHADOW_CONFIGS.items():
            if symbol in state:
                continue # Already tracking an active virtual position

            # Select symbol on MT5 to keep rates updated
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None or tick.bid == 0.0:
                continue

            # Evaluate setup using exact institutional engine logic
            setup = engine.evaluate_institutional_setup(symbol)
            if not setup.get('valid'):
                continue

            direction = setup['direction'] # "BUY" or "SELL"
            lot = cfg['lot']
            dollar_per_pt = get_shadow_dollar_per_pt(symbol, lot)
            if dollar_per_pt <= 0:
                continue

            # Exact risk & target distance matching
            target_tp_dist = cfg['tp_dollars'] / dollar_per_pt
            target_sl_dist = cfg['max_sl_dollars'] / dollar_per_pt

            entry_price = tick.ask if direction == 'BUY' else tick.bid
            if direction == 'BUY':
                sl_price = entry_price - target_sl_dist
                tp_price = entry_price + target_tp_dist
            else:
                sl_price = entry_price + target_sl_dist
                tp_price = entry_price - target_tp_dist

            # Log virtual entry into shadow portfolio
            state[symbol] = {
                "symbol": symbol,
                "name": cfg['name'],
                "direction": direction,
                "lot": lot,
                "dollar_per_pt": dollar_per_pt,
                "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "entry_price": entry_price,
                "current_sl": sl_price,
                "tp_price": tp_price,
                "initial_sl": sl_price,
                "trigger": setup.get('reason', 'Institutional MTF Crossover'),
                "max_profit_usd": 0.0,
                "be_applied": False,
                "lock_applied": False
            }
            save_shadow_state(state)
            logger.info(
                f"[Shadow Order Triggered] {symbol} {direction} @ {entry_price:.4f} | "
                f"SL: {sl_price:.4f} (-${cfg['max_sl_dollars']:.2f}) | "
                f"TP: {tp_price:.4f} (+${cfg['tp_dollars']:.2f}) | (No Live MT5 Order Placed)"
            )

    except Exception as e:
        logger.error(f"[ShadowTracker] Cycle error: {e}")

def generate_shadow_report() -> str:
    """Produces a clean HTML-formatted Telegram summary of shadow tracking performance."""
    history = load_shadow_history()
    state = load_shadow_state()

    lines = [
        "<b>📊 AlphaEdge Shadow Tracking Report</b>",
        "<i>Paper Observation Mode (Zero Live Risk)</i>\n"
    ]

    # Active Shadow Positions
    if state:
        lines.append("<b>Active Virtual Positions:</b>")
        for sym, pos in state.items():
            tick = mt5.symbol_info_tick(sym)
            curr = tick.bid if pos['direction'] == 'BUY' else tick.ask if tick else pos['entry_price']
            pts = (curr - pos['entry_price']) if pos['direction'] == 'BUY' else (pos['entry_price'] - curr)
            fl_usd = pts * pos.get('dollar_per_pt', 1.0)
            lines.append(f"• <b>{sym}</b> {pos['direction']} @ {pos['entry_price']:.4f} | PnL: <b>${fl_usd:+.2f}</b>")
        lines.append("")
    else:
        lines.append("• <i>No open virtual positions currently.</i>\n")

    # Historical Stats Per Asset
    lines.append("<b>Performance Summary:</b>")
    for sym, cfg in SHADOW_CONFIGS.items():
        sym_trades = [t for t in history if t['symbol'] == sym]
        count = len(sym_trades)
        if count == 0:
            lines.append(f"• <b>{cfg['name']} ({sym}):</b> 0 trades logged yet")
            continue

        wins = len([t for t in sym_trades if t['realized_usd'] > 0])
        wr = round((wins / count) * 100, 1)
        net = sum(t['realized_usd'] for t in sym_trades)
        lines.append(f"• <b>{cfg['name']} ({sym}):</b> {count} trades | {wr}% WR | Net: <b>${net:+.2f}</b>")

    lines.append("\n<i>To enable real trading on any asset, simply notify the team.</i>")
    return "\n".join(lines)
