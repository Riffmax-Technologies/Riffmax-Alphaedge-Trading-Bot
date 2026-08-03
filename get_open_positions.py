# get_open_positions.py
"""Utility script to print currently open positions created by the trading bot.
It connects to MetaTrader5 using the same credentials as the bot scripts
and prints any open positions whose comment matches the bot identifiers.
"""

import MetaTrader5 as mt5
from datetime import datetime

# MT5 connection credentials (same as in alphaedge.py / sherifnew_strategy.py)
MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10",
}

def main():
    if not mt5.initialize(**MT5_CONFIG):
        print("[Error] Could not connect to MetaTrader5")
        return

    positions = mt5.positions_get()
    if not positions:
        print("No open positions found.")
        mt5.shutdown()
        return

    print(f"Open positions as of {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    for p in positions:
        comment = getattr(p, "comment", "")
        if comment in ("ALPHAEDGE_TRADE", "SHERIFNEW_UT"):
            side = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
            print(
                f"Ticket {p.ticket} | Symbol {p.symbol} | {side} | "
                f"Lots {p.volume:.2f} | SL {p.sl:.5f} | TP {p.tp:.5f} | "
                f"Comment {comment}"
            )
    mt5.shutdown()

if __name__ == "__main__":
    main()
