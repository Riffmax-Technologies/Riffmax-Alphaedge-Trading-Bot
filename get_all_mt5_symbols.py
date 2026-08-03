# get_all_mt5_symbols.py
import MetaTrader5 as mt5

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    symbols = mt5.symbols_get()
    print(f"Total symbols available: {len(symbols)}")
    
    # Check for some specific popular ones
    candidates = [
        # FX Majors / Minors
        "EURUSD", "AUDUSD", "NZDUSD", "USDJPY", "EURJPY", "GBPJPY", "CHFJPY",
        # Crypto
        "SOLUSD", "XRPUSD", "LTCUSD", "ADAUSD",
        # Indices / Commodities
        "GER30", "DE30", "UK100", "US2000", "NATGAS"
    ]
    
    print("\nCheck specifications of popular candidates:")
    for sym in candidates:
        info = mt5.symbol_info(sym)
        if info:
            print(f"- {sym}: visible={info.visible}, spread={info.spread}, point={info.point}, digits={info.digits}")
        else:
            print(f"- {sym}: NOT FOUND")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
