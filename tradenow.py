import os
import sys
import time
import logging
import pandas as pd
import MetaTrader5 as mt5
from metatrader_client import MT5Client
from metatrader_client.order.send_order import send_order
from metatrader_client.types import TradeRequestActions, OrderType

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradeNowBasket")

# Verified MT5 Credentials
MT5_CONFIG = {
    "login": int(os.getenv('MT5_LOGIN', '0')),
    "password": os.getenv('MT5_PASSWORD', ''),
    "server": os.getenv('MT5_SERVER', ''),
}

# 5 Symbols to Trade
SYMBOLS = ["GBPJPY", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"]

def get_lot_size(symbol: str) -> float:
    symbol_upper = symbol.upper()
    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        return 0.03  # Gold
    elif "BTC" in symbol_upper or "ETH" in symbol_upper:
        return 0.05  # Crypto
    else:
        return 0.1   # Currencies

def get_market_trend_advanced(symbol: str) -> str:
    """
    Advanced Trend Analysis Engine (Short-term M5 Momentum):
    - Calculates 9 EMA and 21 EMA on the M5 (5-minute) timeframe.
    - Calculates RSI (14) on M5 to identify momentum direction.
    - BUY: EMA9 > EMA21 and RSI > 50
    - SELL: EMA9 < EMA21 and RSI < 50
    - Fallback: Uses net direction over the last 3 candles on M5.
    """
    try:
        # Fetch the last 50 candles on the M5 timeframe
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50)
        if rates is None or len(rates) < 21:
            logger.warning(f"Not enough data to run indicators for {symbol}. Falling back to BUY.")
            return "BUY"
            
        df = pd.DataFrame(rates)
        
        # Calculate EMAs
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        last_ema9 = df['ema9'].iloc[-1]
        last_ema21 = df['ema21'].iloc[-1]
        
        # Calculate RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        last_rsi = df['rsi'].iloc[-1]
        
        # Decision Logic
        if last_ema9 > last_ema21 and last_rsi > 50:
            trend = "BUY"
        elif last_ema9 < last_ema21 and last_rsi < 50:
            trend = "SELL"
        else:
            # Fallback: Check price movement over the last 3 bars (M5)
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-4] if len(df) >= 4 else df['open'].iloc[-1]
            trend = "BUY" if last_close > prev_close else "SELL"
            
        logger.info(f"Analysis for {symbol} (M5) - EMA9: {last_ema9:.5f}, EMA21: {last_ema21:.5f}, RSI: {last_rsi:.1f} -> Trend: {trend}")
        return trend
        
    except Exception as e:
        logger.error(f"Advanced trend analysis failed for {symbol}: {e}")
    return "BUY"

def get_sltp_levels(symbol: str, action: str, entry_price: float):
    symbol_upper = symbol.upper()
    action_upper = action.upper()
    
    # Query MT5 for point and digits info
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.00001
    
    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        offset_sl = 5.0   # $5.00 stop loss
        offset_tp = 10.0  # $10.00 take profit
    elif "BTC" in symbol_upper:
        offset_sl = 300.0 # $300 stop loss
        offset_tp = 600.0 # $600 take profit
    else:
        # Forex: 30 pips stop loss, 60 pips take profit (1 pip = 10 points)
        offset_sl = 30 * 10 * point
        offset_tp = 60 * 10 * point
        
    if action_upper == "BUY":
        sl = entry_price - offset_sl
        tp = entry_price + offset_tp
    else:
        sl = entry_price + offset_sl
        tp = entry_price - offset_tp
        
    return round(sl, 5), round(tp, 5)

def main():
    client = MT5Client(MT5_CONFIG)
    try:
        logger.info("Connecting to MetaTrader 5...")
        client.connect()
        logger.info("Successfully connected to MetaTrader 5!")
    except Exception as e:
        logger.error(f"Failed to connect to MT5: {e}")
        sys.exit(1)
        
    basket_id = f"BASKET_{int(time.time())}"
    logger.info(f"Generating new trade basket: {basket_id}")
    
    executed_trades = []
    
    print(f"\n### Executing Basket Trade (Advanced Trend Analysis): {basket_id}")
    print("| Symbol | Action | Volume | Entry Price | Stop Loss (SL) | Take Profit (TP) | Status | Ticket |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for symbol in SYMBOLS:
        if not mt5.symbol_select(symbol, True):
            print(f"| {symbol} | - | - | - | - | - | Failed to select symbol | - |")
            continue
            
        volume = get_lot_size(symbol)
        
        # Analyze trend using advanced indicators
        action = get_market_trend_advanced(symbol)
        order_type = OrderType.BUY if action == "BUY" else OrderType.SELL
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"| {symbol} | {action} | {volume} | - | - | - | Failed to fetch price | - |")
            continue
        price = tick.ask if action == "BUY" else tick.bid
        
        # Calculate SL & TP
        sl, tp = get_sltp_levels(symbol, action, price)
        
        try:
            result = send_order(
                client._connection,
                action=TradeRequestActions.DEAL,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=price,
                stop_loss=sl,
                take_profit=tp,
                comment=basket_id
            )
            
            if result.get("success"):
                response_data = result.get("data")
                ticket = response_data.order if response_data else "Unknown"
                print(f"| {symbol} | **{action}** | {volume} | {price:.5f} | {sl:.5f} | {tp:.5f} | Filled | `{ticket}` |")
                executed_trades.append(ticket)
            else:
                reason = result.get("message", "Unknown error")
                print(f"| {symbol} | {action} | {volume} | {price:.5f} | {sl:.5f} | {tp:.5f} | Failed: {reason} | - |")
                
        except Exception as e:
            print(f"| {symbol} | {action} | {volume} | - | - | - | Execution Error: {e} | - |")
            
    print(f"\nSuccessfully launched **{len(executed_trades)}** trades under basket `{basket_id}`.")
    print("All trades are protected. The server will close all of them if the combined profit reaches >= $10.00.")

    client.disconnect()

if __name__ == "__main__":
    main()
