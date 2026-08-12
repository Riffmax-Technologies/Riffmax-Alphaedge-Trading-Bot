#!/usr/bin/env python3
"""Simple historical backtest that replays M30 bars and simulates entries from `alphaedge` logic.
For each symbol, it scans historical bars, runs the strategy on each bar (using past data only), and when a BUY/SELL signal is found it simulates whether TP or SL was hit within the next `lookahead` bars.
Produces a short CSV summary per symbol.
"""
import os
import sys
import time
import logging
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd

import alphaedge
from trading_bot_skills.indicators import (
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_ema,
    calculate_atr,
    find_support_resistance,
)
from trading_bot_skills.risk import assess_risk

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('Backtest')

TIMEFRAME = mt5.TIMEFRAME_M30
HIST_BARS = 800
LOOKAHEAD = 24  # check next 24 M30 bars (~12 hours)
MIN_BARS = 150

symbols = alphaedge.SYMBOLS

if not mt5.initialize(login=alphaedge.MT5_CONFIG['login'], password=alphaedge.MT5_CONFIG['password'], server=alphaedge.MT5_CONFIG['server']):
    logger.error('MT5 init failed: %s', mt5.last_error())
    sys.exit(1)

results = []
AE_RR_MIN = alphaedge.RISK_REWARD_MIN
PULLBACK_ATR_FRACTION = alphaedge.PULLBACK_ATR_FRACTION
ATR_SL_MULTIPLIER = alphaedge.ATR_SL_MULTIPLIER
for symbol in symbols:
    logger.info('Backtesting %s', symbol)
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, HIST_BARS)
    if rates is None or len(rates) < MIN_BARS:
        logger.warning('Insufficient bars for %s: %s', symbol, len(rates) if rates is not None else 0)
        continue
    # Build DataFrame directly from MT5 rates and sort chronologically by time
    df_all = pd.DataFrame(rates)
    if 'time' in df_all.columns:
        df_all = df_all.sort_values('time').reset_index(drop=True)
    # normalize column names to lowercase where possible
    new_cols = []
    for c in df_all.columns:
        if isinstance(c, str):
            new_cols.append(c.lower())
        else:
            new_cols.append(str(c))
    df_all.columns = new_cols

    # If MT5 close/open/high/low names are missing (e.g., numeric columns), map by position
    expected = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
    if 'close' not in df_all.columns:
        if all(str(i) in df_all.columns for i in range(min(len(df_all.columns), 8))):
            # map first columns by position
            mapping = {str(i): expected[i] for i in range(min(len(expected), len(df_all.columns)))}
            df_all = df_all.rename(columns=mapping)
        else:
            logger.warning('Could not map columns for %s. Columns: %s', symbol, list(df_all.columns))
            continue
    logger.info('Columns for %s after mapping: %s', symbol, list(df_all.columns))
    wins = 0
    losses = 0
    signals = 0
    rr_list = []
    for i in range(MIN_BARS, len(df_all)-LOOKAHEAD-1):
        df_slice = df_all.iloc[:i+1].copy()
        # compute indicators
        df_slice = calculate_bollinger_bands(df_slice)
        df_slice = calculate_rsi(df_slice)
        df_slice = calculate_atr(df_slice)
        last_close = df_slice['close'].iloc[-1]
        last_open = df_slice['open'].iloc[-1]
        prev_close = df_slice['close'].iloc[-2]
        prev_open = df_slice['open'].iloc[-2]
        last_high = df_slice['high'].iloc[-1]
        last_low = df_slice['low'].iloc[-1]
        last_rsi = df_slice['rsi'].iloc[-1]
        last_atr = df_slice['atr'].iloc[-1]
        bb_upper = df_slice['bb_upper'].iloc[-1]
        bb_lower = df_slice['bb_lower'].iloc[-1]
        support, resistance = find_support_resistance(df_slice)

        last_bullish = last_close > last_open
        last_bearish = last_close < last_open
        prev_bullish = prev_close > prev_open
        prev_bearish = prev_close < prev_open
        bullish_reversal = last_bullish and prev_bearish and last_close > prev_close
        bearish_reversal = last_bearish and prev_bullish and last_close < prev_close

        # approximate the improved AlphaEdge signal filters
        is_bottom_zone = (
            last_close <= bb_lower and
            last_low <= (support + (0.35 * last_atr)) and
            last_rsi <= 28 and
            bullish_reversal
        )
        is_top_zone = (
            last_close >= bb_upper and
            last_high >= (resistance - (0.35 * last_atr)) and
            last_rsi >= 72 and
            bearish_reversal
        )

        action = 'NEUTRAL'
        if is_bottom_zone:
            action = 'BUY'
            entry_price = last_close - PULLBACK_ATR_FRACTION * last_atr
            sl = support - (ATR_SL_MULTIPLIER * last_atr)
            tp = resistance - (0.2 * last_atr)
        elif is_top_zone:
            action = 'SELL'
            entry_price = last_close + PULLBACK_ATR_FRACTION * last_atr
            sl = resistance + (ATR_SL_MULTIPLIER * last_atr)
            tp = support + (0.2 * last_atr)
        else:
            continue

        # basic RR filter
        risk = abs(entry_price - sl)
        reward = abs(tp - entry_price)
        if risk <= 0 or (reward / risk) < max(AE_RR_MIN, 4.0):
            continue

        signals += 1
        rr_list.append(reward/risk)

        # simulate lookahead: check if TP or SL hit first
        future = df_all.iloc[i+1:i+1+LOOKAHEAD]
        hit = None
        for idx, row in future.iterrows():
            high = row['high']
            low = row['low']
            if action == 'BUY':
                if low <= sl:
                    hit = 'SL'
                    break
                if high >= tp:
                    hit = 'TP'
                    break
            else:
                if high >= sl:
                    hit = 'SL'
                    break
                if low <= tp:
                    hit = 'TP'
                    break
        if hit == 'TP':
            wins += 1
        elif hit == 'SL':
            losses += 1
        else:
            # neither hit in lookahead -> treat as no outcome
            pass

    results.append({
        'symbol': symbol,
        'signals': signals,
        'wins': wins,
        'losses': losses,
        'win_rate': (wins / signals) if signals else None,
        'avg_rr': (sum(rr_list)/len(rr_list)) if rr_list else None
    })

mt5.shutdown()

out = pd.DataFrame(results)
out.to_csv('backtest_summary.csv', index=False)
logger.info('Backtest complete. Summary written to backtest_summary.csv')
print(out)
