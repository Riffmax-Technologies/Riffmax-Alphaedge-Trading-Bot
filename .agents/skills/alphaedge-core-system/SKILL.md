---
name: alphaedge-core-system
description: Documents the exact indicators, timeframes, entry rules, SL/TP rules, 0.5% lot-size calculation, trading sessions, and asset filtering for the AlphaEdge Core Trading System. Use this to understand the logic of the system or when modifying the trading engine.
---

# AlphaEdge Unified Core Trading System

This skill documents the complete AlphaEdge unified trading methodology. This system was designed to consolidate multiple disparate strategies into a single, high-probability institutional framework applied across Forex, Indices, Metals, and Crypto.

## 1. Asset & Session Filtering

To prevent the bot from forcing trades during low-volume periods, the system operates on a strict Watchlist + Session constraint.

**Sessions (Based on UTC time):**
- **London Session (07:00 - 16:00 UTC):** Active for EURUSDm, GBPUSDm, XAUUSDm, XAGUSDm, USDJPYm, AUDUSDm
- **New York Session (13:00 - 22:00 UTC):** Active for USTECm (NAS100), USOILm, XAUUSDm, XAGUSDm, USDJPYm, USDCADm
- **24/7 Session:** Active for BTCUSDm, ETHUSDm

*The scanner will ONLY analyze assets that are currently in an active session.*

## 2. Dynamic Risk Management (0.5% Rule)

**Lot sizing is never fixed.** The bot reads the live account balance and risks exactly **0.5%** per trade.

**Calculation:**
1. Determine `risk_usd = balance * 0.005`
2. Determine `price_distance = abs(entry_price - stop_loss)`
3. Convert distance to ticks and calculate `loss_for_one_lot`
4. `optimal_volume = risk_usd / loss_for_one_lot`
5. Clamp volume between broker's `volume_min` and `volume_max`.

*If the ATR dictates a wider stop loss, the lot size automatically shrinks to maintain the exact 0.5% risk.*

## 3. The 6-Step Core Strategy Logic

The algorithm (`analyze_core_system_df` in `alphaedge.py`) looks for the following sequential setup:

### Step 1: Higher Timeframe Bias
- Calculated using the 50 EMA and 200 EMA.
- **Bullish Bias:** 50 EMA > 200 EMA
- **Bearish Bias:** 50 EMA < 200 EMA

### Step 2: Mark Liquidity Levels
- The system fetches Daily (D1) data to mark the **Previous Day High (PDH)** and **Previous Day Low (PDL)**.

### Step 3 & 4: Liquidity Sweep & Displacement
- The system analyzes the most recent 15 candles.
- **Bearish Trigger:** Price sweeps above the PDH and immediately rejects (closes below the PDH and below the 50 EMA).
- **Bullish Trigger:** Price sweeps below the PDL and immediately rejects (closes above the PDL and above the 50 EMA).

### Step 5 & 6: Structure Confirmation & Retest Entry
- Instead of entering on the breakout, the system enters on the structural retest.
- **Entry Price:** The current closing price after the rejection/displacement candle confirms the trend reversal.

## 4. Stop Loss & Take Profit (ATR Adjusted)

- **Stop Loss:** Placed exactly **0.5 ATR** beyond the sweep extreme.
  - *Buy SL:* `sweep_low - (0.5 * ATR)`
  - *Sell SL:* `sweep_high + (0.5 * ATR)`
- **Take Profit:** Projected at a strict **2:1 Risk/Reward Ratio**.
  - *Buy TP:* `entry_price + 2.0 * (entry_price - sl)`
  - *Sell TP:* `entry_price - 2.0 * (sl - entry_price)`
