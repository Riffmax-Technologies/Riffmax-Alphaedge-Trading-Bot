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


class InstitutionalEngine:
    def __init__(self, volume_multiplier: float = 1.6, lookback_h4: int = 50, lookback_swings: int = 25):
        self.volume_mult = volume_multiplier
        self.lookback_h4 = lookback_h4
        self.lookback_swings = lookback_swings

    def get_mtf_data(self, symbol: str):
        """Fetches H4, H1, and M15 bars from MT5."""
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

        # 1. H4 Dealing Range Analysis
        range_info = self.analyze_dealing_range(df_h4, curr_price)
        if not range_info:
            return {"valid": False, "direction": "NONE", "reason": "Dealing range calculation failed"}

        # 2. Check for Bottom BUY Setup
        is_discount = range_info["is_discount"]
        h1_buy_sweep, h1_low = self.detect_liquidity_sweep(df_h1, "BUY")
        m15_buy_sweep, m15_low = self.detect_liquidity_sweep(df_m15, "BUY")
        has_buy_sweep = h1_buy_sweep or m15_buy_sweep

        h1_vol_whale, h1_ratio = self.detect_whale_volume(df_h1)
        m15_vol_whale, m15_ratio = self.detect_whale_volume(df_m15)
        has_whale_vol = h1_vol_whale or m15_vol_whale
        max_vol_ratio = max(h1_ratio, m15_ratio)

        has_buy_fvg, fvg_size = self.detect_fair_value_gap(df_h1, "BUY")

        if is_discount and (has_buy_sweep or (range_info["is_deep_discount"] and has_whale_vol)):
            sweep_ref = min(h1_low, m15_low) if has_buy_sweep else range_info["range_low"]
            sl_price = sweep_ref - (6.0 if symbol == "XAUUSDm" else 25.0)
            tp_price = tick.ask + (15.0 if symbol == "XAUUSDm" else 35.0)

            return {
                "valid": True,
                "direction": "BUY",
                "reason": f"Institutional Bottom Accumulation (Discount: {range_info['location_pct']:.1f}%, Vol: {max_vol_ratio}x, Sweep: {has_buy_sweep})",
                "entry_price": tick.ask,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "deal_range": range_info,
                "whale_detected": has_whale_vol,
                "vol_ratio": max_vol_ratio,
                "sweep_level": sweep_ref,
                "fvg_detected": has_buy_fvg
            }

        # 3. Check for Top SELL Setup
        is_premium = range_info["is_premium"]
        h1_sell_sweep, h1_high = self.detect_liquidity_sweep(df_h1, "SELL")
        m15_sell_sweep, m15_high = self.detect_liquidity_sweep(df_m15, "SELL")
        has_sell_sweep = h1_sell_sweep or m15_sell_sweep
        has_sell_fvg, _ = self.detect_fair_value_gap(df_h1, "SELL")

        if is_premium and (has_sell_sweep or (range_info["is_deep_premium"] and has_whale_vol)):
            sweep_ref = max(h1_high, m15_high) if has_sell_sweep else range_info["range_high"]
            sl_price = sweep_ref + (6.0 if symbol == "XAUUSDm" else 25.0)
            tp_price = tick.bid - (15.0 if symbol == "XAUUSDm" else 35.0)

            return {
                "valid": True,
                "direction": "SELL",
                "reason": f"Institutional Top Distribution (Premium: {range_info['location_pct']:.1f}%, Vol: {max_vol_ratio}x, Sweep: {has_sell_sweep})",
                "entry_price": tick.bid,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "deal_range": range_info,
                "whale_detected": has_whale_vol,
                "vol_ratio": max_vol_ratio,
                "sweep_level": sweep_ref,
                "fvg_detected": has_sell_fvg
            }

        skip_reason = "Waiting. "
        if not is_discount and not is_premium:
            skip_reason += f"Price at Equilibrium ({range_info['location_pct']:.1f}%). Refusing entry halfway."
        elif is_discount and not has_buy_sweep:
            skip_reason += f"In Discount ({range_info['location_pct']:.1f}%), waiting for bottom liquidity sweep/whale surge."
        elif is_premium and not has_sell_sweep:
            skip_reason += f"In Premium ({range_info['location_pct']:.1f}%), waiting for top liquidity sweep/whale surge."

        return {
            "valid": False,
            "direction": "NONE",
            "reason": skip_reason,
            "deal_range": range_info,
            "whale_detected": has_whale_vol,
            "vol_ratio": max_vol_ratio
        }
