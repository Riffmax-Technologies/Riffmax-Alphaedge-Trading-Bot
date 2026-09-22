"""
institutional_engine.py — Institutional Multi-Timeframe (MTF) & Whale Flow Analysis Engine
=============================================================================================
Identifies high-conviction structural swing setups:
1. Multi-Timeframe (MTF) Top-Down Structure:
   - H4: Macro Trend & Dealing Range (Premium vs Discount Zone).
         STRICT RULE: BUY orders are ONLY permitted in the Discount Zone (< 50% equilibrium).
                      SELL orders are ONLY permitted in the Premium Zone (> 50% equilibrium).
                      Never buy halfway or chase extended highs!
   - H1: Key Structural Levels (Swing Highs & Lows, Liquidity Pools).
   - M15: Sniper Entry Confirmation (Liquidity Sweep + Bullish/Bearish Displacement).
2. Whale Flow & Volume Climax Detection:
   - Liquidity Sweeps (Stop Hunts): Price pierces a key swing low/high to absorb retail stop orders,
     then immediately rejects back inside the range.
   - Climax Tick Volume: Volume on the sweep/reversal candle >= 1.8x the 20-period moving average.
   - Fair Value Gap (FVG) / Displacement: Strong institutional expansion confirming market participation.
"""

import logging
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

logger = logging.getLogger("AlphaEdge.Institutional")


def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Computes Average True Range (ATR) over the last `period` completed bars.
    True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    Returns 0.0 if data is insufficient.
    """
    if df is None or len(df) < period + 2:
        return 0.0
    highs  = df['high'].astype(float).values
    lows   = df['low'].astype(float).values
    closes = df['close'].astype(float).values
    trs = []
    for i in range(1, len(highs)):
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i]  - closes[i - 1])
        trs.append(max(hl, hpc, lpc))
    # Use the last `period` TR values for a simple ATR
    return float(np.mean(trs[-period:]))



class InstitutionalEngine:
    def __init__(self, volume_multiplier: float = 1.6, lookback_h4: int = 50, lookback_swings: int = 25):
        self.volume_mult = volume_multiplier
        self.lookback_h4 = lookback_h4
        self.lookback_swings = lookback_swings

    def get_mtf_data(self, symbol: str):
        """Fetches H4, H1, and M15 bars from MT5."""
        mt5.symbol_select(symbol, True)
        h4_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 100)
        h1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 150)
        m15_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 150)

        if h4_rates is None or h1_rates is None or m15_rates is None:
            return None

        return {
            "H4": pd.DataFrame(h4_rates),
            "H1": pd.DataFrame(h1_rates),
            "M15": pd.DataFrame(m15_rates)
        }

    def analyze_dealing_range(self, df_h4: pd.DataFrame, current_price: float):
        """
        Calculates the H4 Dealing Range:
        - Range High, Range Low, Equilibrium (50%).
        - Returns whether current price is in Discount (< 50%) or Premium (> 50%).
        """
        recent_h4 = df_h4.tail(self.lookback_h4)
        range_high = float(recent_h4['high'].max())
        range_low = float(recent_h4['low'].min())
        spread_range = range_high - range_low

        if spread_range <= 0:
            return None

        equilibrium = range_low + (0.5 * spread_range)
        discount_threshold = range_low + (0.45 * spread_range)  # Deep discount zone
        premium_threshold = range_high - (0.45 * spread_range)   # Deep premium zone

        location_pct = ((current_price - range_low) / spread_range) * 100.0

        is_discount = current_price < equilibrium
        is_deep_discount = current_price <= discount_threshold
        is_premium = current_price > equilibrium
        is_deep_premium = current_price >= premium_threshold

        return {
            "range_high": range_high,
            "range_low": range_low,
            "equilibrium": equilibrium,
            "location_pct": location_pct,
            "is_discount": is_discount,
            "is_deep_discount": is_deep_discount,
            "is_premium": is_premium,
            "is_deep_premium": is_deep_premium
        }

    def detect_whale_volume(self, df: pd.DataFrame, idx: int = -2):
        """
        Checks if candle at idx has institutional/whale volume (relative to 20 SMA).
        Index -2 is the latest fully closed candle.
        """
        if len(df) < 25:
            return False, 1.0

        volumes = df['tick_volume'].astype(float).values
        vol_sma20 = np.mean(volumes[idx - 20:idx])
        curr_vol = volumes[idx]

        vol_ratio = curr_vol / vol_sma20 if vol_sma20 > 0 else 1.0
        is_whale = vol_ratio >= self.volume_mult

        return is_whale, round(float(vol_ratio), 2)

    def detect_liquidity_sweep(self, df: pd.DataFrame, direction: str = "BUY"):
        """
        Detects if a swing low (for BUY) or swing high (for SELL) was swept by the last closed candle:
        - For BUY: Candle low pierced below previous swing low, but closed ABOVE the swing low (rejection).
        - For SELL: Candle high pierced above previous swing high, but closed BELOW the swing high.
        """
        if len(df) < self.lookback_swings + 5:
            return False, 0.0

        # Last closed candle is at index -2
        test_candle = df.iloc[-2]
        c_low = float(test_candle['low'])
        c_high = float(test_candle['high'])
        c_close = float(test_candle['close'])
        c_open = float(test_candle['open'])

        # Previous window for swing points (excluding test candle)
        prev_window = df.iloc[- (self.lookback_swings + 2): -2]

        if direction == "BUY":
            swing_low = float(prev_window['low'].min())
            # Liquidity Sweep condition: pierced below swing low, but closed back above it
            swept = (c_low < swing_low) and (c_close > swing_low)
            # Rejection wick validation (lower wick >= 35% of candle range)
            candle_range = c_high - c_low
            lower_wick = min(c_open, c_close) - c_low
            has_rejection_wick = (lower_wick / candle_range >= 0.35) if candle_range > 0 else False

            if swept or (c_low <= swing_low * 1.0005 and has_rejection_wick and c_close > c_open):
                return True, swing_low
            return False, swing_low

        elif direction == "SELL":
            swing_high = float(prev_window['high'].max())
            swept = (c_high > swing_high) and (c_close < swing_high)
            candle_range = c_high - c_low
            upper_wick = c_high - max(c_open, c_close)
            has_rejection_wick = (upper_wick / candle_range >= 0.35) if candle_range > 0 else False

            if swept or (c_high >= swing_high * 0.9995 and has_rejection_wick and c_close < c_open):
                return True, swing_high
            return False, swing_high

        return False, 0.0

    def detect_fair_value_gap(self, df: pd.DataFrame, direction: str = "BUY"):
        """
        Identifies recent Fair Value Gap (FVG) / Imbalance within last 5 candles.
        Bullish FVG: Candle[i-2].high < Candle[i].low (gap between bar 1 and bar 3).
        Bearish FVG: Candle[i-2].low > Candle[i].high.
        """
        if len(df) < 10:
            return False, 0.0

        for i in range(-2, -7, -1):
            if direction == "BUY":
                c1_high = float(df['high'].iloc[i - 2])
                c3_low = float(df['low'].iloc[i])
                if c3_low > c1_high:
                    gap_size = c3_low - c1_high
                    return True, gap_size
            elif direction == "SELL":
                c1_low = float(df['low'].iloc[i - 2])
                c3_high = float(df['high'].iloc[i])
                if c3_high < c1_low:
                    gap_size = c1_low - c3_high
                    return True, gap_size

        return False, 0.0

    def compute_ut_bot_signal(self, df: pd.DataFrame, key_value: float = 1.0, atr_period: int = 10) -> str:
        """
        UT Bot Alerts — Pure Python implementation of QuantNomad's UT Bot.
        Uses an ATR trailing stop to detect confirmed momentum reversals.

        Parameters:
            key_value   : Sensitivity multiplier (default 1.0 = standard, higher = fewer signals)
            atr_period  : ATR period (default 10, matching TradingView default)

        Returns:
            "BUY"  — price just crossed ABOVE the trailing stop (confirmed upward reversal)
            "SELL" — price just crossed BELOW the trailing stop (confirmed downward reversal)
            "NONE" — no confirmed signal on the latest completed bar

        Logic (mirrors TradingView Pine Script):
            nLoss = key_value * ATR(atr_period)
            if close > prev_stop and prev_close > prev_stop:
                stop = max(prev_stop, close - nLoss)
            elif close < prev_stop and prev_close < prev_stop:
                stop = min(prev_stop, close + nLoss)
            else:
                stop = close - nLoss  if close > prev_stop  else close + nLoss

            BUY  = prev_close < prev_stop and close > stop   (cross above)
            SELL = prev_close > prev_stop and close < stop   (cross below)
        """
        min_bars = atr_period + 5
        if df is None or len(df) < min_bars:
            return "NONE"

        closes = df['close'].astype(float).values
        highs  = df['high'].astype(float).values
        lows   = df['low'].astype(float).values

        # Compute ATR for every bar
        trs = [0.0]
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i]  - closes[i-1]))
            trs.append(tr)

        # Simple rolling ATR (period-window mean of TR)
        atrs = []
        for i in range(len(trs)):
            start = max(0, i - atr_period + 1)
            atrs.append(float(np.mean(trs[start:i+1])))

        # Build trailing stop array
        stops = [0.0] * len(closes)
        stops[0] = closes[0]

        for i in range(1, len(closes)):
            n_loss   = key_value * atrs[i]
            prev_c   = closes[i-1]
            c        = closes[i]
            prev_s   = stops[i-1]

            if c > prev_s and prev_c > prev_s:
                stops[i] = max(prev_s, c - n_loss)
            elif c < prev_s and prev_c < prev_s:
                stops[i] = min(prev_s, c + n_loss)
            else:
                stops[i] = c - n_loss if c > prev_s else c + n_loss

        # Check last 3 completed bars for crossover or prevailing trend
        # Index -2 is the latest fully confirmed/closed bar
        i = len(closes) - 2
        if i < 2:
            return "NONE"

        curr_close = closes[i]
        curr_stop  = stops[i]
        
        # Detect fresh crossover on the latest completed bar (index -2)
        # Prevents re-entering into an already established trend after a trade closes!
        if closes[i - 1] <= stops[i - 1] and closes[i] > stops[i]:
            return "BUY"
        elif closes[i - 1] >= stops[i - 1] and closes[i] < stops[i]:
            return "SELL"

        return "NONE"

    def evaluate_institutional_setup(self, symbol: str):
        """
        Comprehensive Institutional Setup Evaluation:
        Returns structured dictionary.
        """
        mtf = self.get_mtf_data(symbol)
        if not mtf:
            return {"valid": False, "direction": "NONE", "reason": "Failed to fetch MTF data"}

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"valid": False, "direction": "NONE", "reason": "No tick data"}

        curr_price = tick.bid
        df_h4 = mtf["H4"]
        df_h1 = mtf["H1"]
        df_m15 = mtf["M15"]

        # 1. H4 Macro Bias & Dealing Range Analysis
        range_info = self.analyze_dealing_range(df_h4, curr_price)
        if not range_info:
            return {"valid": False, "direction": "NONE", "reason": "Dealing range calculation failed"}

        # H4 Macro Trend & Momentum Filter (EMAs + Price Action Structure)
        h4_closes = df_h4['close'].astype(float).values
        h4_highs = df_h4['high'].astype(float).values
        h4_lows  = df_h4['low'].astype(float).values
        
        # Calculate H4 EMAs (EMA 20 & EMA 50)
        ema20_h4 = pd.Series(h4_closes).ewm(span=20).mean().iloc[-1]
        ema50_h4 = pd.Series(h4_closes).ewm(span=50).mean().iloc[-1]
        
        # Calculate H1 EMAs for micro-structure confirmation
        h1_closes = df_h1['close'].astype(float).values
        ema20_h1 = pd.Series(h1_closes).ewm(span=20).mean().iloc[-1]
        ema50_h1 = pd.Series(h1_closes).ewm(span=50).mean().iloc[-1]

        # Multi-bar swing structure
        is_higher_highs = h4_highs[-2] > h4_highs[-4] and h4_lows[-2] > h4_lows[-4]
        is_lower_lows = h4_highs[-2] < h4_highs[-4] and h4_lows[-2] < h4_lows[-4]

        # Pure Trend Bias:
        # BULLISH if price > EMA50 and EMA20 >= EMA50 (or clean higher highs/lows)
        # BEARISH if price < EMA50 and EMA20 <= EMA50 (or clean lower highs/lows)
        if (curr_price > ema50_h4 and ema20_h4 >= ema50_h4) or is_higher_highs:
            h4_trend = "BULLISH"
        elif (curr_price < ema50_h4 and ema20_h4 <= ema50_h4) or is_lower_lows:
            h4_trend = "BEARISH"
        else:
            h4_trend = "RANGE"

        # STRICT TREND & PRICE ACTION RULE:
        # Never trade counter-trend!
        # When H4 trend is BULLISH -> ONLY BUY orders are allowed (even if price is at premium, we ride the trend or buy pullbacks). SELL is STRICTLY FORBIDDEN!
        # When H4 trend is BEARISH -> ONLY SELL orders are allowed. BUY is STRICTLY FORBIDDEN!
        # When H4 is in a neutral RANGE -> Use Dealing Range (BUY in discount <50%, SELL in premium >50%).
        if h4_trend == "BULLISH":
            macro_buy_allowed = True
            macro_sell_allowed = False
        elif h4_trend == "BEARISH":
            macro_buy_allowed = False
            macro_sell_allowed = True
        else:
            # RANGE_BOUND: Only trade at extremes of the range
            macro_buy_allowed = range_info["is_discount"]
            macro_sell_allowed = range_info["is_premium"]

        # 2. M15 / H1 Micro Actionable Trigger Evaluation
        m15_buy_sweep, m15_low = self.detect_liquidity_sweep(df_m15, "BUY")
        m15_sell_sweep, m15_high = self.detect_liquidity_sweep(df_m15, "SELL")
        h1_buy_sweep, h1_low = self.detect_liquidity_sweep(df_h1, "BUY")
        h1_sell_sweep, h1_high = self.detect_liquidity_sweep(df_h1, "SELL")

        m15_vol_whale, m15_ratio = self.detect_whale_volume(df_m15)
        h1_vol_whale, h1_ratio = self.detect_whale_volume(df_h1)
        has_whale_vol = m15_vol_whale or h1_vol_whale
        max_vol_ratio = max(m15_ratio, h1_ratio)

        has_buy_fvg, _ = self.detect_fair_value_gap(df_m15, "BUY")
        has_sell_fvg, _ = self.detect_fair_value_gap(df_m15, "SELL")

        # M15 & H1 UT Bot Momentum Signals
        ut_signal_m15 = self.compute_ut_bot_signal(df_m15, key_value=1.0, atr_period=10)
        ut_signal_h1  = self.compute_ut_bot_signal(df_h1,  key_value=1.0, atr_period=10)

        # M15 ATR for responsive sniper SL calculation
        m15_atr = _compute_atr(df_m15, period=14)
        is_gold = symbol == "XAUUSDm"
        if is_gold:
            min_sl_pts = 12.0   # 12.0 pts ($24 USD at 0.02 lot) structural buffer on Gold
            min_tp_pts = 20.0   # 20.0 pts ($40 USD at 0.02 lot)
        else:
            min_sl_pts = 80.0   # 80.0 pts ($27.50 USD at 0.30 lot) wide structural SL beyond noise reach
            min_tp_pts = 72.0   # 72.0 pts ($25.00 USD at 0.30 lot) institutional target
        sl_buffer = max(round(m15_atr * 1.5, 4), min_sl_pts)

        # Institutional Volume Gate: Gold fires freely on UT Bot signal alone (high liquidity).
        # DAX requires institutional volume participation to filter out noise entries.
        whale_gate_ok = is_gold or has_whale_vol

        # ── BUY SETUP EVALUATION ──────────────────────────────────────────────
        # Conditions: Macro BUY allowed AND (M15/H1 Liquidity Sweep Wick Rejection OR M15 UT Bot BUY)
        has_buy_trigger = (m15_buy_sweep or h1_buy_sweep or ut_signal_m15 == "BUY")
        if macro_buy_allowed and has_buy_trigger and whale_gate_ok:
            sweep_ref = min(m15_low, h1_low) if (m15_buy_sweep or h1_buy_sweep) else (curr_price - sl_buffer)
            # SL is anchored BEYOND the lowest wick point of the sweep
            sl_price = sweep_ref - sl_buffer

            # Target 1.5x R:R or full institutional swing target
            sl_dist = abs(tick.ask - sl_price)
            if sl_dist > 0:
                tp_offset = max(sl_dist * 1.5, min_tp_pts)
                tp_price = tick.ask + tp_offset

                trigger_type = "Liquidity Sweep Wick Rejection" if (m15_buy_sweep or h1_buy_sweep) else f"M15 UT Bot {ut_signal_m15}"
                logger.info(
                    f"[InstitutionalEngine] BUY Triggered! {symbol} | H4: {h4_trend} ({range_info['location_pct']:.1f}%) | "
                    f"Trigger: {trigger_type} | Entry: {tick.ask:.2f} | SL: {sl_price:.2f} | TP: {tp_price:.2f} (R:R {tp_offset/sl_dist:.2f})"
                )

                return {
                    "valid": True,
                    "direction": "BUY",
                    "reason": f"H4 Bias {h4_trend} ({range_info['location_pct']:.1f}%) + {trigger_type}",
                    "entry_price": tick.ask,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "deal_range": range_info,
                    "whale_detected": has_whale_vol,
                    "vol_ratio": max_vol_ratio,
                    "sweep_level": sweep_ref,
                    "fvg_detected": has_buy_fvg,
                    "ut_bot": ut_signal_m15
                }

        # ── SELL SETUP EVALUATION ─────────────────────────────────────────────
        # Conditions: Macro SELL allowed AND (M15/H1 Liquidity Sweep Wick Rejection OR M15 UT Bot SELL)
        has_sell_trigger = (m15_sell_sweep or h1_sell_sweep or ut_signal_m15 == "SELL")
        if macro_sell_allowed and has_sell_trigger and whale_gate_ok:
            sweep_ref = max(m15_high, h1_high) if (m15_sell_sweep or h1_sell_sweep) else (curr_price + sl_buffer)
            # SL is anchored BEYOND the highest wick point of the sweep
            sl_price = sweep_ref + sl_buffer

            sl_dist = abs(sl_price - tick.bid)
            if sl_dist > 0:
                tp_offset = max(sl_dist * 1.5, min_tp_pts)
                tp_price = tick.bid - tp_offset

                trigger_type = "Liquidity Sweep Wick Rejection" if (m15_sell_sweep or h1_sell_sweep) else f"M15 UT Bot {ut_signal_m15}"
                logger.info(
                    f"[InstitutionalEngine] SELL Triggered! {symbol} | H4: {h4_trend} ({range_info['location_pct']:.1f}%) | "
                    f"Trigger: {trigger_type} | Entry: {tick.bid:.2f} | SL: {sl_price:.2f} | TP: {tp_price:.2f} (R:R {tp_offset/sl_dist:.2f})"
                )

                return {
                    "valid": True,
                    "direction": "SELL",
                    "reason": f"H4 Bias {h4_trend} ({range_info['location_pct']:.1f}%) + M15 UT Bot {ut_signal_m15} Trigger",
                    "entry_price": tick.bid,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "deal_range": range_info,
                    "whale_detected": has_whale_vol,
                    "vol_ratio": max_vol_ratio,
                    "sweep_level": sweep_ref,
                    "fvg_detected": has_sell_fvg,
                    "ut_bot": ut_signal_m15
                }

        skip_reason = (
            f"Waiting for alignment. H4: {h4_trend} (Eq: {range_info['location_pct']:.1f}%), "
            f"M15 UT: {ut_signal_m15}, Sweeps: B={m15_buy_sweep}/S={m15_sell_sweep}."
        )

        return {
            "valid": False,
            "direction": "NONE",
            "reason": skip_reason,
            "deal_range": range_info,
            "whale_detected": has_whale_vol,
            "vol_ratio": max_vol_ratio
        }
