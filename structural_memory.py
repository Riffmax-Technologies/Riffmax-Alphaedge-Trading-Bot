"""
structural_memory.py -- AlphaEdge Institutional Memory Module
=============================================================
Tracks multi-week price structure for institutional confluence:
  - Previous Week High / Low  (W1 bar[-2])
  - Previous Day High / Low   (D1 bar[-2])
  - Asian Session High / Low  (M15 bars 21:00-05:00 UTC)
  - Market Regime             (EXPANSION_UP / EXPANSION_DOWN / RANGE_BOUND)
  - Weekly Equilibrium        (midpoint of current W1 range)

Runs independently of trade session. Updated every cycle so the bot
always has full institutional context even during off-hours observation.
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(__file__), "structural_memory_state.json")

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    _MT5_AVAILABLE = False
    logger.warning("[StructuralMemory] MetaTrader5 not available.")


def _empty_symbol_state():
    return {
        "pwh": None,
        "pwl": None,
        "pdh": None,
        "pdl": None,
        "asia_high": None,
        "asia_low": None,
        "weekly_eq": None,
        "regime": "UNKNOWN",
        "last_updated": None,
    }


class StructuralMemory:
    """
    Maintains persistent multi-timeframe price structure for each symbol.
    Observation runs 24/5 independent of trading session.
    """

    def __init__(self):
        self._state = self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                logger.info("[StructuralMemory] Loaded state from disk.")
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[StructuralMemory] Failed to load state: {e}")
        return {}

    def _save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"[StructuralMemory] Failed to save state: {e}")

    def update_structure(self, symbol):
        if not _MT5_AVAILABLE:
            return False
        if symbol not in self._state:
            self._state[symbol] = _empty_symbol_state()
        ctx = self._state[symbol]
        try:
            # Previous Week High/Low
            w1_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 3)
            if w1_bars is not None and len(w1_bars) >= 2:
                prev_week = w1_bars[-2]
                ctx["pwh"] = float(prev_week["high"])
                ctx["pwl"] = float(prev_week["low"])
                cur_week = w1_bars[-1]
                ctx["weekly_eq"] = round((float(cur_week["high"]) + float(cur_week["low"])) / 2, 5)

            # Previous Day High/Low
            d1_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)
            if d1_bars is not None and len(d1_bars) >= 2:
                prev_day = d1_bars[-2]
                ctx["pdh"] = float(prev_day["high"])
                ctx["pdl"] = float(prev_day["low"])

            # Asian Session Range
            ctx["asia_high"], ctx["asia_low"] = self._compute_asian_range(symbol)

            # Market Regime
            ctx["regime"] = self._compute_regime(symbol)

            ctx["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"[StructuralMemory] update_structure({symbol}) error: {e}")
            return False

    def _compute_asian_range(self, symbol):
        try:
            m15_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 64)
            if m15_bars is None or len(m15_bars) == 0:
                return None, None
            highs, lows = [], []
            for bar in m15_bars:
                bar_time = datetime.fromtimestamp(bar["time"], tz=timezone.utc)
                hour = bar_time.hour
                if hour >= 21 or hour < 5:
                    highs.append(float(bar["high"]))
                    lows.append(float(bar["low"]))
            if highs and lows:
                return max(highs), min(lows)
            return None, None
        except Exception as e:
            logger.error(f"[StructuralMemory] Asian range error ({symbol}): {e}")
            return None, None

    def _compute_regime(self, symbol):
        try:
            h4_bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 50)
            if h4_bars is None or len(h4_bars) < 20:
                return "UNKNOWN"
            import pandas as pd
            df = pd.DataFrame(h4_bars)
            closes = df['close'].astype(float).values
            highs  = df['high'].astype(float).values
            lows   = df['low'].astype(float).values
            
            ema20 = pd.Series(closes).ewm(span=20).mean().iloc[-1]
            ema50 = pd.Series(closes).ewm(span=50).mean().iloc[-1]
            curr_c = closes[-1]
            
            hh = highs[-2] > highs[-4]
            hl = lows[-2] > lows[-4]
            ll = lows[-2] < lows[-4]
            lh = highs[-2] < highs[-4]
            
            if (curr_c > ema50 and ema20 >= ema50) or (hh and hl):
                return "EXPANSION_UP"
            elif (curr_c < ema50 and ema20 <= ema50) or (ll and lh):
                return "EXPANSION_DOWN"
            else:
                return "RANGE_BOUND"
        except Exception as e:
            logger.error(f"[StructuralMemory] Regime error ({symbol}): {e}")
            return "UNKNOWN"

    def get_context(self, symbol):
        if symbol not in self._state:
            self._state[symbol] = _empty_symbol_state()
            self.update_structure(symbol)
            return self._state[symbol]
        ctx = self._state[symbol]
        if ctx.get("last_updated"):
            try:
                last = datetime.fromisoformat(ctx["last_updated"])
                age = (datetime.now(timezone.utc) - last).total_seconds()
                if age > 900:
                    self.update_structure(symbol)
            except (ValueError, TypeError):
                self.update_structure(symbol)
        else:
            self.update_structure(symbol)
        return self._state[symbol]

    def is_in_weekly_discount(self, symbol, price):
        ctx = self.get_context(symbol)
        eq = ctx.get("weekly_eq")
        if eq is None:
            return True
        return price < eq

    def is_in_weekly_premium(self, symbol, price):
        ctx = self.get_context(symbol)
        eq = ctx.get("weekly_eq")
        if eq is None:
            return True
        return price > eq

    def is_above_pwh(self, symbol, price):
        ctx = self.get_context(symbol)
        pwh = ctx.get("pwh")
        return pwh is not None and price > pwh

    def is_below_pwl(self, symbol, price):
        ctx = self.get_context(symbol)
        pwl = ctx.get("pwl")
        return pwl is not None and price < pwl

    def is_above_pdh(self, symbol, price):
        ctx = self.get_context(symbol)
        pdh = ctx.get("pdh")
        return pdh is not None and price > pdh

    def is_below_pdl(self, symbol, price):
        ctx = self.get_context(symbol)
        pdl = ctx.get("pdl")
        return pdl is not None and price < pdl

    def is_asia_breakout_bull(self, symbol, price):
        ctx = self.get_context(symbol)
        ah = ctx.get("asia_high")
        return ah is not None and price > ah

    def is_asia_breakout_bear(self, symbol, price):
        ctx = self.get_context(symbol)
        al = ctx.get("asia_low")
        return al is not None and price < al

    def summary(self, symbol):
        ctx = self.get_context(symbol)
        lines = [
            f"[StructuralMemory] {symbol} @ {ctx.get('last_updated', 'N/A')}",
            f"  Regime     : {ctx.get('regime', 'UNKNOWN')}",
            f"  PWH / PWL  : {ctx.get('pwh')} / {ctx.get('pwl')}",
            f"  PDH / PDL  : {ctx.get('pdh')} / {ctx.get('pdl')}",
            f"  Asia H/L   : {ctx.get('asia_high')} / {ctx.get('asia_low')}",
            f"  Weekly EQ  : {ctx.get('weekly_eq')}",
        ]
        return "\n".join(lines)
