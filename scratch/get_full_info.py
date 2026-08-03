import MetaTrader5 as mt5
import pandas as pd

def get_diagnostics():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    term_info = mt5.terminal_info()
    acc_info = mt5.account_info()
    
    print("\n==================================")
    print("=== MT5 TERMINAL CONFIGURATION ===")
    print("==================================")
    if term_info:
        for k, v in term_info._asdict().items():
            print(f"{k}: {v}")
    else:
        print("No terminal info available.")
        
    print("\n===============================")
    print("=== MT5 ACCOUNT CONFIGURATION ===")
    print("===============================")
    if acc_info:
        for k, v in acc_info._asdict().items():
            print(f"{k}: {v}")
    else:
        print("No account info available.")
        
    mt5.shutdown()

if __name__ == "__main__":
    get_diagnostics()
