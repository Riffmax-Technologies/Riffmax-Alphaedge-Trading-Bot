# check_active_positions.py
import MetaTrader5 as mt5
import pandas as pd

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def check():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    positions = mt5.positions_get()
    if not positions:
        print("No open positions.")
    else:
        df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
        print("=== Current Open Positions ===")
        print(df[['ticket', 'symbol', 'type', 'volume', 'price_open', 'price_current', 'sl', 'tp', 'profit', 'comment']].to_string(index=False))
        
    mt5.shutdown()

if __name__ == "__main__":
    check()
