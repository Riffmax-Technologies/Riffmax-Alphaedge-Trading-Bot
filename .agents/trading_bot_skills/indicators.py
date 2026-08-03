# Indicator utilities for trading bots
import pandas as pd

def calculate_bollinger_bands(df, period=20, num_std=2):
    """Calculate Bollinger Bands (middle, upper, lower)."""
    df['bb_mid'] = df['close'].rolling(window=period).mean()
    df['bb_std'] = df['close'].rolling(window=period).std()
    df['bb_upper'] = df['bb_mid'] + (num_std * df['bb_std'])
    df['bb_lower'] = df['bb_mid'] - (num_std * df['bb_std'])
    return df

def calculate_rsi(df, period=14):
    """Calculate Relative Strength Index (RSI)."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calculate_ema(df, period=9):
    """Calculate Exponential Moving Average (EMA)."""
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    """Calculate Average True Range (ATR)."""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = true_range.rolling(window=period).mean()
    return df

def find_support_resistance(df, window=20):
    """Detect support and resistance levels using local extrema over recent candles."""
    last_idx = len(df) - 1
    recent_df = df.iloc[max(0, last_idx - 100):]
    supports = []
    resistances = []
    for i in range(window, len(recent_df) - window):
        chunk = recent_df.iloc[i - window : i + window + 1]
        center = recent_df.iloc[i]
        if center['low'] == chunk['low'].min():
            supports.append(center['low'])
        if center['high'] == chunk['high'].max():
            resistances.append(center['high'])
    current_close = df['close'].iloc[-1]
    valid_supports = [s for s in supports if s < current_close]
    valid_resistances = [r for r in resistances if r > current_close]
    support = max(valid_supports) if valid_supports else df['low'].rolling(window=window).min().iloc[-1]
    resistance = min(valid_resistances) if valid_resistances else df['high'].rolling(window=window).max().iloc[-1]
    return support, resistance
