# get_metals_structure.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

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
        
    for symbol in ["XAUUSD", "XAGUSD"]:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 100)
        if rates is None or len(rates) == 0:
            print(f"Failed for {symbol}")
            continue
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # S/R pivots
        pivots_high = []
        pivots_low = []
        for i in range(2, len(df)-2):
            if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
                pivots_high.append(high[i])
            if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
                pivots_low.append(low[i])
                
        current_price = close[-1]
        
        # Calculate Bollinger Bands
        sma = df['close'].rolling(20).mean().values
        std = df['close'].rolling(20).std().values
        upper_bb = sma + 2 * std
        lower_bb = sma - 2 * std
        
        # Calculate RSI
        rsi = calculate_rsi(close, 14)
        
        print(f"\n=== {symbol} M30 Metals Analysis ===")
        print(f"Current Price: {current_price:.3f}")
        print(f"BB: Lower={lower_bb[-1]:.3f} | Mid={sma[-1]:.3f} | Upper={upper_bb[-1]:.3f}")
        print(f"RSI: {rsi[-1]:.2f}")
        
        # Did it break out or hit support?
        # A buy signal on AlphaEdge requires:
        # 1. Price sweeps a recent support pivot (Swing Low) OR is at the lower BB band.
        # 2. RSI is oversold (< 30) or showing bullish divergence.
        # 3. Setup is confirmed by a bullish reversal candle at support.
        
        # Let's look at recent swing lows:
        recent_lows = [l for l in pivots_low if l < current_price]
        if recent_lows:
            print(f"Recent Swing Low (Support Pivot): {max(recent_lows):.3f}")
        else:
            print("No recent swing low support pivot found.")
            
        # Is price currently at support or resistance?
        if current_price > sma[-1]:
            print("Price status: Trading above the 20 SMA (Bullish expansion phase).")
        else:
            print("Price status: Trading below the 20 SMA.")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
