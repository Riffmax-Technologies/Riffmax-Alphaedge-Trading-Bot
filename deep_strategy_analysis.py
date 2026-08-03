# deep_strategy_analysis.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys, os

scratch_dir = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch"
if scratch_dir not in sys.path:
    sys.path.insert(0, scratch_dir)

from alphaedge import calculate_bollinger_bands, calculate_rsi, calculate_atr, find_support_resistance, calculate_ema

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def analyze_structural_precision(symbol):
    rates_30 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 150)
    rates_5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 150)
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 150)
    
    if rates_30 is None or rates_5 is None or rates_h1 is None:
        print(f"Failed to copy rates for {symbol}")
        return
        
    df30 = pd.DataFrame(rates_30)
    df30 = calculate_bollinger_bands(df30)
    df30 = calculate_rsi(df30)
    df30 = calculate_atr(df30)
    support, resistance = find_support_resistance(df30)
    
    df5 = pd.DataFrame(rates_5)
    df5['ema5'] = calculate_ema(df5, 5)
    df5['ema13'] = calculate_ema(df5, 13)
    df5 = calculate_rsi(df5)
    
    # H1
    dfh1 = pd.DataFrame(rates_h1)
    dfh1['sma20'] = dfh1['close'].rolling(window=20).mean()
    dfh1 = calculate_rsi(dfh1)
    
    last_close = df30['close'].iloc[-1]
    bb_lower = df30['bb_lower'].iloc[-1]
    bb_upper = df30['bb_upper'].iloc[-1]
    rsi30 = df30['rsi'].iloc[-1]
    
    print(f"\n==================== {symbol} DEEP SCAN ====================")
    print(f"Price: {last_close:.5f} | M30 BB: [{bb_lower:.5f} - {bb_upper:.5f}]")
    print(f"M30 RSI: {rsi30:.1f} | Support: {support:.5f} | Resistance: {resistance:.5f}")
    
    # M5 stats
    ema5_last = df5['ema5'].iloc[-1]
    ema13_last = df5['ema13'].iloc[-1]
    rsi5_last = df5['rsi'].iloc[-1]
    print(f"M5 EMA5: {ema5_last:.5f} | EMA13: {ema13_last:.5f} (Diff: {ema5_last - ema13_last:.5f}) | M5 RSI: {rsi5_last:.1f}")
    
    # H1 stats
    h1_close = dfh1['close'].iloc[-1]
    h1_sma = dfh1['sma20'].iloc[-1]
    h1_rsi = dfh1['rsi'].iloc[-1]
    print(f"H1 Close: {h1_close:.5f} | H1 SMA20: {h1_sma:.5f} | H1 RSI: {h1_rsi:.1f}")

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    for sym in ["XAUUSD", "XAGUSD", "BTCUSD", "US500", "EURUSD"]:
        analyze_structural_precision(sym)
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
