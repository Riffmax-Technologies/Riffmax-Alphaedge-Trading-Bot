import MetaTrader5 as mt5
import pandas as pd

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

if not mt5.initialize(login=MT5_CONFIG["login"], password=MT5_CONFIG["password"], server=MT5_CONFIG["server"]):
    print("Failed to initialize MT5")
    exit(1)

print("Connected to MT5")

# Check positions
positions = mt5.positions_get()
if positions is None:
    print("No positions found or error")
elif len(positions) == 0:
    print("No active positions.")
else:
    print(f"Total active positions: {len(positions)}")
    df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
    if not df.empty:
        print(df[['ticket', 'symbol', 'type', 'volume', 'price_open', 'sl', 'tp', 'profit', 'comment']])

# Check symbol details for the 5 symbols
symbols = ["GBPJPY", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"]
for s in symbols:
    info = mt5.symbol_info(s)
    if info:
        print(f"Symbol: {s}, Digits: {info.digits}, Point: {info.point}")
    else:
        print(f"Symbol {s} not found")

mt5.shutdown()
