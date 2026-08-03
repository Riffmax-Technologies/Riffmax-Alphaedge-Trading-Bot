# get_symbols_status.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

scratch_dir = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch"
import sys, os
if scratch_dir not in sys.path:
    sys.path.insert(0, scratch_dir)

from alphaedge import calculate_bollinger_bands, calculate_rsi, calculate_atr, find_support_resistance

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def analyze_symbol_proximity(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 150)
    if rates is None or len(rates) < 50:
        print(f"{symbol}: Insufficient data")
        return
        
    df = pd.DataFrame(rates)
    df = calculate_bollinger_bands(df)
    df = calculate_rsi(df)
    df = calculate_atr(df)
    
    last_close = df['close'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    bb_upper = df['bb_upper'].iloc[-1]
    bb_lower = df['bb_lower'].iloc[-1]
    support, resistance = find_support_resistance(df)
    
    print(f"\n--- {symbol} Proximity Analysis ---")
    print(f"Current Price: {last_close:.5f}")
    print(f"RSI (Target <=32 for BUY, >=68 for SELL): Current = {last_rsi:.1f}")
    print(f"Bollinger Bands: Lower = {bb_lower:.5f} | Upper = {bb_upper:.5f}")
    print(f"Support/Resistance: Support = {support:.5f} | Resistance = {resistance:.5f}")
    
    # Distance to thresholds
    dist_to_buy_rsi = max(0, last_rsi - 32)
    dist_to_sell_rsi = max(0, 68 - last_rsi)
    dist_to_lower_bb = last_close - bb_lower
    dist_to_upper_bb = bb_upper - last_close
    
    print(f"Proximity to BUY Zone: Price is {dist_to_lower_bb:.5f} above Lower BB. RSI is {dist_to_buy_rsi:.1f} points away.")
    print(f"Proximity to SELL Zone: Price is {dist_to_upper_bb:.5f} below Upper BB. RSI is {dist_to_sell_rsi:.1f} points away.")

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    for symbol in ["XAUUSD", "XAGUSD", "BTCUSD", "EURUSD", "US500"]:
        analyze_symbol_proximity(symbol)
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
