"""Analyze closed trades from the previous MT5 account and compute failure modes.

Connects to the legacy account (credentials embedded in `tradenow.py`) and computes
per-position statistics including profit, duration, and adverse excursion (max
move against the position during its lifetime) using M5 price data.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import MetaTrader5 as mt5


import os

# Use .env / environment variables when available (Deriv demo credentials)
MT5_CONFIG = {
    'login': int(os.getenv('MT5_LOGIN', '0')),
    'password': os.getenv('MT5_PASSWORD', ''),
    'server': os.getenv('MT5_SERVER', '')
}


def connect_old():
    try:
        ok = mt5.initialize(login=MT5_CONFIG['login'], password=MT5_CONFIG['password'], server=MT5_CONFIG['server'])
        if not ok:
            print('MT5 initialize failed:', mt5.last_error())
            return False
        return True
    except Exception as e:
        print('MT5 connection error:', e)
        return False


def analyze(days=180, limit_positions=200):
    if not connect_old():
        return

    now = datetime.now()
    start = now - timedelta(days=days)
    print(f'Fetching deals from {start} to {now}...')
    deals = mt5.history_deals_get(start, now)
    if not deals:
        print('No deals found in the requested period.')
        mt5.shutdown()
        return

    # Convert namedtuples to dicts so pandas preserves field names
    df = pd.DataFrame([d._asdict() for d in deals])
    # Ensure time fields are datetime
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], unit='s')

    print(f'Deals returned: {len(df)}')
    print('Columns:', list(df.columns))
    if len(df) > 0:
        print(df.head().to_string())

    # Choose grouping column: prefer position_id, fall back to 'ticket' or 'order'
    if 'position_id' in df.columns:
        group_col = 'position_id'
    elif 'ticket' in df.columns:
        group_col = 'ticket'
    elif 'order' in df.columns:
        group_col = 'order'
    else:
        # last resort: group by symbol+time
        group_col = None

    positions = []
    if group_col:
        for pid, group in df.groupby(group_col):
            if pid is None:
                continue
            group = group.sort_values('time')
            open_row = group.iloc[0]
            close_row = group.iloc[-1]
            symbol = open_row['symbol']
            entry_price = open_row['price'] if 'price' in open_row else None
            exit_price = close_row['price'] if 'price' in close_row else None
            profit = group['profit'].sum() if 'profit' in group else 0.0
            entry_time = open_row['time'] if 'time' in open_row else None
            exit_time = close_row['time'] if 'time' in close_row else None
            positions.append({'position_id': pid, 'symbol': symbol, 'entry_time': entry_time, 'exit_time': exit_time, 'entry_price': entry_price, 'exit_price': exit_price, 'profit': profit})

    else:
        # approximate grouping by symbol and entry time
        for _, row in df.iterrows():
            pid_val = getattr(row, group_col, None) if group_col else row.get('order', None)
            sym = row.get('symbol', None)
            entry_time = row.get('time', None)
            entry_price = row.get('price', None)
            profit_val = row.get('profit', 0.0)
            positions.append({'position_id': pid_val, 'symbol': sym, 'entry_time': entry_time, 'exit_time': entry_time, 'entry_price': entry_price, 'exit_price': entry_price, 'profit': profit_val})
    positions = sorted(positions, key=lambda x: x['entry_time'] or now, reverse=True)[:limit_positions]

    results = []
    for pos in positions:
        sym = pos['symbol']
        et = pos['entry_time']
        xt = pos['exit_time']
        if not et or not xt:
            continue
        # Fetch M5 candles covering the trade lifetime plus small buffer
        try:
            rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, int((et - timedelta(minutes=5)).timestamp()), int((xt + timedelta(minutes=5)).timestamp()))
        except Exception:
            rates = None
        adverse = None
        if rates is not None and len(rates) > 0:
            df_rates = pd.DataFrame(rates)
            entry_price = float(pos['entry_price']) if pos['entry_price'] is not None else None
            if entry_price is None:
                adverse = None
            else:
                low = df_rates['low'].min()
                high = df_rates['high'].max()
                adverse_buy = low - entry_price
                adverse_sell = high - entry_price
                adverse = {'adverse_buy': adverse_buy, 'adverse_sell': adverse_sell}
        results.append({**pos, 'adverse': adverse})

    # Summary
    df_res = pd.DataFrame(results)
    if df_res.empty:
        print('No positions analyzed.')
        mt5.shutdown()
        return

    total = len(df_res)
    wins = df_res[df_res['profit'] > 0]
    losses = df_res[df_res['profit'] <= 0]
    print(f'Total positions analyzed: {total}\nWins: {len(wins)} Losses: {len(losses)}')
    print(f'Average profit per trade: {df_res["profit"].mean():.2f}')

    # Adverse excursion summary (where available)
    adverse_vals = []
    for r in results:
        a = r.get('adverse')
        if isinstance(a, dict):
            adverse_vals.append(a['adverse_buy'])
    if adverse_vals:
        import numpy as np
        arr = np.array(adverse_vals)
        print(f'Average adverse excursion (buy-side sample): {arr.mean():.5f}')

    # Save results to CSV for inspection
    out_path = os.path.join(os.path.dirname(__file__), 'old_account_analysis.csv')
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f'Analysis written to {out_path}')
    # Try to notify summary via Telegram (if bot is configured)
    try:
        from alphaedge import send_telegram_alert
        summary = f"📊 <b>Old Account Analysis</b>\nPositions: {total} | Wins: {len(wins)} | Losses: {len(losses)} | Avg P/T: {df_res['profit'].mean():.2f}"
        send_telegram_alert(summary)
    except Exception:
        pass
    mt5.shutdown()


if __name__ == '__main__':
    analyze(days=365, limit_positions=200)
