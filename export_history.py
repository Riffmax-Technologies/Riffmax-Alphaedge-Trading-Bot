# export_history.py
"""Fetches MetaTrader5 trade history for the bot's trades and writes a CSV.
The script:
1. Connects to MT5 using the same credentials as the bots.
2. Retrieves all deals (both entry and exit) for the current account.
3. Groups deals by position ID to identify complete trades.
4. Filters only trades whose comment matches our bot identifiers
   (ALPHAEDGE_TRADE or SHERIFNEW_UT).
5. Calculates profit, win/loss flag, and writes a CSV named
   `bot_trade_history.csv` in the same directory.
"""

import csv
import os
from collections import defaultdict
import MetaTrader5 as mt5
from datetime import datetime

# MT5 credentials – same as used in the bot scripts
MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10",
}

def main():
    if not mt5.initialize(**MT5_CONFIG):
        print("[Error] Could not connect to MetaTrader5")
        return

    # Get all deals for this account (default: from the beginning of time)
    # Using a broad date range to capture everything.
    start = datetime(2000, 1, 1)
    end = datetime.now()
    deals = mt5.history_deals_get(start, end)
    if deals is None:
        print("[Error] No deals returned")
        mt5.shutdown()
        return

    # Group deals by position_id (each trade may have entry and exit deals)
    positions = defaultdict(list)
    for d in deals:
        positions[d.position_id].append(d)

    # Prepare rows for CSV
    rows = []
    for pos_id, ds in positions.items():
        # Identify the comment (should be same for all deals in a trade)
        comment = ds[0].comment
        if comment not in ("ALPHAEDGE_TRADE", "SHERIFNEW_UT"):
            continue
        # Determine entry and exit prices and profit
        entry_price = None
        exit_price = None
        profit = 0.0
        for d in ds:
            if d.entry == 0:  # entry deal
                entry_price = d.price
            else:  # exit deal (1 = close, 3 = partially close)
                exit_price = d.price
            profit += d.profit
        if entry_price is None:
            continue
        # Determine win/loss
        result = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
        rows.append({
            "position_id": pos_id,
            "symbol": ds[0].symbol,
            "comment": comment,
            "entry_price": entry_price,
            "exit_price": exit_price if exit_price is not None else "",
            "profit": profit,
            "result": result,
            "timestamp": datetime.fromtimestamp(ds[0].time).isoformat()
        })

    # Write CSV
    csv_path = os.path.join(os.path.dirname(__file__), "bot_trade_history.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "position_id", "symbol", "comment", "entry_price",
            "exit_price", "profit", "result", "timestamp"
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Exported {len(rows)} bot trades to {csv_path}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
