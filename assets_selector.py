"""Select top N assets by recent ATR for training or focused scanning.
This script queries available symbols via MT5 and ranks them by ATR on M30 timeframe.
"""
from __future__ import annotations
import MetaTrader5 as mt5
import pandas as pd


def select_top_assets(count: int = 30, timeframe=mt5.TIMEFRAME_M30, lookback=100):
    symbols = [s.name for s in mt5.symbols_get() if s.visible]
    scores = []
    for sym in symbols:
        try:
            rates = mt5.copy_rates_from_pos(sym, timeframe, 0, lookback)
            if rates is None or len(rates) < 20:
                continue
            df = pd.DataFrame(rates)
            # ATR calculation (14)
            df['tr1'] = (df['high'] - df['low']).abs()
            df['tr2'] = (df['high'] - df['close'].shift(1)).abs()
            df['tr3'] = (df['low'] - df['close'].shift(1)).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            atr = df['tr'].rolling(window=14).mean().iloc[-1]
            if pd.isna(atr):
                continue
            scores.append((sym, atr))
        except Exception:
            continue
    # Sort by ATR descending (higher volatility instruments first)
    scores.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scores[:count]]


if __name__ == '__main__':
    if not mt5.initialize():
        print('MT5 not initialized; please connect first')
    else:
        top = select_top_assets(30)
        print('Top assets:', top)
        mt5.shutdown()
