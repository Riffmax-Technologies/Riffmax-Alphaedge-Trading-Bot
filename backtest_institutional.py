"""
backtest_institutional.py
=========================
Historical Backtester simulating the EXACT institutional strategy currently deployed:
- Asset: Gold (XAUUSDm) ONLY
- Multi-Timeframe Structure: H4 EMA trend (EMA20/EMA50) + M15 micro trigger
- Micro Trigger: M15 UT Bot Crossover & Liquidity Sweeps
- SL & TP: Pure Dollar Values
    * Gold (0.02 lot): Target $60.00 TP, $36.00 SL (18 pts room), BE at $20, Lock $25 at $35
- Cooldown: 60-minute post-trade cooldown
- No midway entry: only enter on fresh crossover/sweep alignment
"""

import sys
import os
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from institutional_trader import ASSET_CONFIGS, get_dollar_per_pt
from institutional_engine import InstitutionalEngine

def run_simulation(symbol, lookback_bars=2500):
    if not mt5.initialize():
        print(f"Failed to initialize MT5: {mt5.last_error()}")
        return

    cfg = ASSET_CONFIGS[symbol]
    lot = cfg['lot']
    tp_usd = cfg['tp_dollars']
    sl_usd = cfg['max_sl_dollars']
    be_usd = cfg['be_trigger_dollars']
    lock_trigger_usd = cfg['lock_trigger_dollars']
    lock_amount_usd = cfg['lock_amount_dollars']

    dollar_per_pt = get_dollar_per_pt(symbol, lot)
    
    tp_pts = tp_usd / dollar_per_pt
    sl_pts = sl_usd / dollar_per_pt
    be_pts = be_usd / dollar_per_pt
    lock_trigger_pts = lock_trigger_usd / dollar_per_pt
    lock_amount_pts = lock_amount_usd / dollar_per_pt

    print(f"\n=======================================================")
    print(f"  BACKTESTING INSTITUTIONAL STRATEGY: {symbol}")
    print(f"=======================================================")
    print(f"  Lot Size: {lot}")
    print(f"  Dollar / Point: ${dollar_per_pt:.4f}")
    print(f"  Target Profit (TP): ${tp_usd:.2f} ({tp_pts:.1f} pts)")
    print(f"  Initial Risk (SL):  ${sl_usd:.2f} ({sl_pts:.1f} pts)")
    print(f"  Break-Even Trigger: ${be_usd:.2f} ({be_pts:.1f} pts)")
    print(f"  Profit Lock Trigger: ${lock_trigger_usd:.2f} -> Lock ${lock_amount_usd:.2f}")

    # Fetch M15 historical bars
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, lookback_bars)
    if rates is None or len(rates) < 300:
        print(f"Insufficient rates for {symbol}")
        return

    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    engine = InstitutionalEngine()
    
    # Pre-calculate UT Bot stops on M15
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    # UT Bot calculation
    key_value = 1.0
    atr_period = 10
    
    # ATR
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hpc, lpc))
    
    atrs = []
    for i in range(n):
        start = max(0, i - atr_period + 1)
        atrs.append(float(np.mean(trs[start:i+1])))
        
    stops = [0.0] * n
    stops[0] = closes[0]
    for i in range(1, n):
        n_loss = key_value * atrs[i]
        prev_c = closes[i-1]
        c = closes[i]
        prev_s = stops[i-1]
        if c > prev_s and prev_c > prev_s:
            stops[i] = max(prev_s, c - n_loss)
        elif c < prev_s and prev_c < prev_s:
            stops[i] = min(prev_s, c + n_loss)
        else:
            stops[i] = c - n_loss if c > prev_s else c + n_loss

    # Iterate chronologically through bars simulating execution
    trades = []
    in_trade = False
    cooldown_until_idx = 0
    trade_info = {}

    start_idx = 100
    for i in range(start_idx, n - 1):
        curr_time = df['datetime'].iloc[i]
        curr_close = closes[i]
        curr_high = highs[i]
        curr_low = lows[i]

        # If in a trade, evaluate position lifecycle
        if in_trade:
            pos_type = trade_info['type']
            entry_price = trade_info['entry']
            current_sl = trade_info['sl']
            current_tp = trade_info['tp']
            
            # Check high/low of this candle against SL and TP
            hit_tp = False
            hit_sl = False
            exit_price = 0.0

            if pos_type == "BUY":
                # Check BE / Profit Lock progression
                max_pts_reached = curr_high - entry_price
                if max_pts_reached >= lock_trigger_pts:
                    locked_sl = entry_price + lock_amount_pts
                    if locked_sl > current_sl:
                        current_sl = locked_sl
                        trade_info['sl'] = locked_sl
                elif max_pts_reached >= be_pts:
                    be_sl = entry_price + (0.5 if symbol == "XAUUSDm" else 10.0)
                    if be_sl > current_sl:
                        current_sl = be_sl
                        trade_info['sl'] = be_sl

                # Check exits
                if curr_low <= current_sl:
                    hit_sl = True
                    exit_price = current_sl
                elif curr_high >= current_tp:
                    hit_tp = True
                    exit_price = current_tp

            else: # SELL
                max_pts_reached = entry_price - curr_low
                if max_pts_reached >= lock_trigger_pts:
                    locked_sl = entry_price - lock_amount_pts
                    if locked_sl < current_sl:
                        current_sl = locked_sl
                        trade_info['sl'] = locked_sl
                elif max_pts_reached >= be_pts:
                    be_sl = entry_price - (0.5 if symbol == "XAUUSDm" else 10.0)
                    if be_sl < current_sl:
                        current_sl = be_sl
                        trade_info['sl'] = be_sl

                if curr_high >= current_sl:
                    hit_sl = True
                    exit_price = current_sl
                elif curr_low <= current_tp:
                    hit_tp = True
                    exit_price = current_tp

            if hit_tp or hit_sl:
                pts_pnl = (exit_price - entry_price) if pos_type == "BUY" else (entry_price - exit_price)
                usd_pnl = pts_pnl * dollar_per_pt
                outcome = "WIN" if usd_pnl > 0 else "LOSS"
                trade_info['exit_time'] = curr_time
                trade_info['exit_price'] = exit_price
                trade_info['pnl_pts'] = pts_pnl
                trade_info['pnl_usd'] = usd_pnl
                trade_info['outcome'] = outcome
                trades.append(trade_info)
                
                in_trade = False
                # 60-minute post-closure cooldown (4 M15 bars)
                cooldown_until_idx = i + 4
                continue

        # If not in trade and not in cooldown, check setup
        if not in_trade and i >= cooldown_until_idx:
            # 1. Fresh UT Bot Crossover check on bar i
            ut_signal = "NONE"
            if closes[i - 1] <= stops[i - 1] and closes[i] > stops[i]:
                ut_signal = "BUY"
            elif closes[i - 1] >= stops[i - 1] and closes[i] < stops[i]:
                ut_signal = "SELL"

            if ut_signal == "NONE":
                continue

            # 2. H4 Macro Bias Approximation (last 80 M15 bars = 20 H4 bars range)
            window_slice = df.iloc[max(0, i - 120): i]
            range_high = float(window_slice['high'].max())
            range_low = float(window_slice['low'].min())
            spread = range_high - range_low
            if spread <= 0:
                continue
            eq = range_low + 0.5 * spread
            loc_pct = ((curr_close - range_low) / spread) * 100.0

            # Rule: BUY only in Discount (< 50%), SELL only in Premium (> 50%)
            if ut_signal == "BUY" and curr_close > eq:
                continue
            if ut_signal == "SELL" and curr_close < eq:
                continue

            # Session filter: strictly 8:00 AM to 8:00 PM EAT (Monday - Friday)
            eat_hour = (curr_time.hour + 3) % 24
            if curr_time.weekday() in (5, 6) or eat_hour < 8 or eat_hour >= 20:
                continue

            # Valid setup found! Enter at next bar open or current close
            entry_price = curr_close
            if ut_signal == "BUY":
                sl_price = entry_price - sl_pts
                tp_price = entry_price + tp_pts
            else:
                sl_price = entry_price + sl_pts
                tp_price = entry_price - tp_pts

            in_trade = True
            trade_info = {
                "symbol": symbol,
                "type": ut_signal,
                "entry_time": curr_time,
                "entry": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "location_pct": loc_pct
            }

    # Summary Statistics
    total_trades = len(trades)
    if total_trades == 0:
        print(f"No trades triggered for {symbol} under current strict institutional parameters.")
        return

    wins = [t for t in trades if t['pnl_usd'] > 0]
    losses = [t for t in trades if t['pnl_usd'] <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0

    total_profit = sum(t['pnl_usd'] for t in wins)
    total_loss = abs(sum(t['pnl_usd'] for t in losses))
    net_pnl = sum(t['pnl_usd'] for t in trades)
    profit_factor = (total_profit / total_loss) if total_loss > 0 else 999.0

    print(f"\n--- RESULTS SUMMARY ({symbol}) ---")
    print(f"  Total Trades:     {total_trades}")
    print(f"  Wins:             {win_count} ({win_rate:.1f}%)")
    print(f"  Losses:           {loss_count} ({100.0 - win_rate:.1f}%)")
    print(f"  Gross Profit:     ${total_profit:.2f}")
    print(f"  Gross Loss:       ${total_loss:.2f}")
    print(f"  Net Profit (USD): ${net_pnl:.2f}")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"  Avg Trade PnL:    ${net_pnl / total_trades:.2f}")

    # Print sample of last 5 trades
    print("\n  Sample Recent Trades:")
    for t in trades[-5:]:
        print(f"    {t['entry_time'].strftime('%Y-%m-%d %H:%M')} | {t['type']} @ {t['entry']:.2f} | Out @ {t['exit_price']:.2f} | {t['outcome']} (${t['pnl_usd']:+.2f})")

if __name__ == "__main__":
    run_simulation("XAUUSDm", lookback_bars=3000)
