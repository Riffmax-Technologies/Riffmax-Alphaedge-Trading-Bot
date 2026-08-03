# get_btc_chart.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    symbol = "BTCUSD"
    # Select symbol
    mt5.symbol_select(symbol, True)
    
    # Get last 50 bars on M30 (which is AlphaEdge's timeframe) and H1
    for tf_name, tf in [("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1)]:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 50)
        if rates is None or len(rates) == 0:
            print(f"Failed to copy rates for {symbol} on {tf_name}")
            continue
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # Calculate Bollinger Bands
        sma = df['close'].rolling(20).mean().values
        std = df['close'].rolling(20).std().values
        upper_bb = sma + 2 * std
        lower_bb = sma - 2 * std
        
        # Calculate RSI
        rsi = calculate_rsi(close, 14)
        
        # Current status
        current_price = close[-1]
        last_upper = upper_bb[-1]
        last_lower = lower_bb[-1]
        last_rsi = rsi[-1]
        
        # S/R pivots (Highs/Lows)
        pivots_high = []
        pivots_low = []
        for i in range(2, len(df)-2):
            if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
                pivots_high.append(high[i])
            if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
                pivots_low.append(low[i])
                
        nearest_resistance = min([h for h in pivots_high if h > current_price], default=max(high))
        nearest_support = max([l for l in pivots_low if l < current_price], default=min(low))
        
        print(f"\n=== {symbol} {tf_name} Analysis ===")
        print(f"Current Price: {current_price:.2f}")
        print(f"Nearest Support (Pivot): {nearest_support:.2f} (Distance: {current_price - nearest_support:.2f})")
        print(f"Nearest Resistance (Pivot): {nearest_resistance:.2f} (Distance: {nearest_resistance - current_price:.2f})")
        print(f"Bollinger Bands: Lower={last_lower:.2f} | Mid={sma[-1]:.2f} | Upper={last_upper:.2f}")
        print(f"RSI (14): {last_rsi:.2f}")
        
        # Trend Regime
        if current_price > sma[-1] and last_rsi > 50:
            print("Trend Regime: BULLISH (Price above mid-band, RSI > 50)")
        elif current_price < sma[-1] and last_rsi < 40:
            print("Trend Regime: BEARISH (Price below mid-band, RSI < 40)")
        else:
            print("Trend Regime: CONSOLIDATION / NEUTRAL")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
