# M5 Pullback & Confirmation Refinement Implementation Plan

## 1. Objective
Refine the AlphaEdge institutional execution engine using **Multi-Timeframe Fractal Confirmation (M15 Setup -> M5 Pullback Turn)** to eliminate premature entries, prevent getting stopped out during normal retests, and add **US30m** to live trading alongside **XAUUSDm** and **USOILm**. Run comprehensive 1-month, 2-month, and 3-month backtests across all 3 assets to validate performance.

---

## 2. Architecture & Design

### A. M5 Pullback & Confirmation Mechanics
1. **M15 Macro / Structural Gate (The "Where" & "What"):**
   - H4 Dealing Range & Trend Bias
   - M15 Liquidity Sweep Wick Rejection OR M15 UT Bot Crossover
   - Strict Discount (<50%, <65% for BUY) / Strict Premium (>50%, >35% for SELL)
   - Whale volume ratio calculation

2. **M5 Micro Confirmation (The "When" - Sniper Trigger):**
   - When M15 setup fires, engine fetches latest closed M5 candles.
   - For **BUY**:
     - Retracement check: Verifies that price has pulled back into discount of the M15 trigger range (or at least 1-2 M5 pullback/pause bars).
     - Micro-reversal trigger: Latest closed M5 candle breaks above previous M5 candle's high (`close > high[-2]` or bullish close reversing downward momentum).
     - Entry price: Close of the confirming M5 candle.
   - For **SELL**:
     - Retracement check: Verifies that price has pulled back into premium of the M15 trigger range (or at least 1-2 M5 pullback/pause bars).
     - Micro-reversal trigger: Latest closed M5 candle breaks below previous M5 candle's low (`close < low[-2]` or bearish close reversing upward momentum).
     - Entry price: Close of the confirming M5 candle.

### B. Asset Matrix & Risk Configuration (Equal $36 Risk / $60 Target)
| Asset | Lot Size | Value per Point | Max SL ($36) | Target TP ($60) | BE Trigger ($20) | Lock Trigger ($35) | Locked Profit ($25) |
|---|---|---|---|---|---|---|---|
| **XAUUSDm** (Gold) | 0.02 | $2.00 / pt | 18.0 pts ($36) | 30.0 pts ($60) | 10.0 pts ($20) | 17.5 pts ($35) | 12.5 pts ($25) |
| **USOILm** (Crude Oil) | 0.05 | $50.00 / pt | $0.72 ($36) | $1.20 ($60) | $0.40 ($20) | $0.70 ($35) | $0.50 ($25) |
| **US30m** (Dow Jones) | 0.25 | $0.25 / pt | 144.0 pts ($36) | 240.0 pts ($60) | 80.0 pts ($20) | 140.0 pts ($35) | 100.0 pts ($25) |

---

## 3. Implementation Steps
1. **`institutional_engine.py`**:
   - Update `get_mtf_data` to fetch M5 rates alongside M15, H1, H4.
   - Implement `verify_m5_pullback_confirmation(df_m5, direction)` helper.
   - Integrate M5 check into `evaluate_institutional_setup()`.
   - Update asset-aware point limits for US30m (`min_sl_pts=144.0`, `min_tp_pts=240.0`).
2. **`institutional_trader.py`**:
   - Add `"US30m"` to `ASSET_CONFIGS`.
3. **`shadow_tracker.py`**:
   - Remove US30m from shadow configs (now traded live alongside Gold and Oil; only EURUSDm remains in shadow).
4. **`news_catalyst_engine.py`**:
   - Ensure US30m maps correctly to `USD` events (already matches `'US' in symbol`).
5. **`alphaedge.py`**:
   - Update startup banner & Telegram alerts to reflect 3 live assets (XAUUSDm, USOILm, US30m).
6. **`_health_check.py`**:
   - Update tests to verify all 3 live asset configs and M5 verification logic.
7. **Comprehensive Multi-Period Backtester (`backtest_institutional.py`)**:
   - Upgrade backtester to run 1-month (~30 days), 2-month (~60 days), and 3-month (~90 days) on XAUUSDm, USOILm, and US30m comparing previous direct entry vs new M5-confirmed entry.
8. **Git commit & push**:
   - Commit changes and push to `master`.
