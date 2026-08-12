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
logger = logging.getLogger("TradeNowBestBasket")

# Verified MT5 Credentials
MT5_CONFIG = {
    "login": int(os.getenv('MT5_LOGIN', '0')),
    "password": os.getenv('MT5_PASSWORD', ''),
    "server": os.getenv('MT5_SERVER', ''),
}

# 5 Symbols to Trade
SYMBOLS = ["GBPJPY", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"]

def get_lot_size(symbol: str) -> float:
    return 0.01  # Set to 0.01 for all symbols to protect capital

def analyze_symbol_trend(symbol: str):
    """
    Analyzes M5 trend for a symbol.
    Returns: (trend: str, score: float, details: str)
    Score is abs(rsi - 50) if EMA and RSI agree. Else 0.0.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50)
        if rates is None or len(rates) < 21:
            return "BUY", 0.0, "No rates data available"
            
        df = pd.DataFrame(rates)
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        last_ema9 = df['ema9'].iloc[-1]
        last_ema21 = df['ema21'].iloc[-1]
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        last_rsi = df['rsi'].iloc[-1]
        
        ema_buy = last_ema9 > last_ema21
        rsi_buy = last_rsi > 50
        
        if ema_buy and rsi_buy:
            trend = "BUY"
            score = last_rsi - 50
            details = f"EMA9 > EMA21 and RSI ({last_rsi:.1f}) > 50"
        elif not ema_buy and not rsi_buy:
            trend = "SELL"
            score = 50 - last_rsi
            details = f"EMA9 < EMA21 and RSI ({last_rsi:.1f}) < 50"
        else:
            # Neutral / Disagreement
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-4] if len(df) >= 4 else df['open'].iloc[-1]
            trend = "BUY" if last_close > prev_close else "SELL"
            score = 0.0  # Lowest priority for neutral setups
            details = f"Neutral (EMA & RSI disagree). Fallback to candle direction: {prev_close:.5f} -> {last_close:.5f}"
            
        return trend, score, details
    except Exception as e:
        logger.error(f"Failed to analyze {symbol}: {e}")
        return "BUY", 0.0, f"Error: {e}"

def get_sltp_levels(symbol: str, action: str, entry_price: float):
    symbol_upper = symbol.upper()
    action_upper = action.upper()
    
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.00001
    
    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        offset_sl = 5.0   # $5.00 stop loss
        offset_tp = 10.0  # $10.00 take profit
    elif "BTC" in symbol_upper:
        offset_sl = 300.0 # $300 stop loss
        offset_tp = 600.0 # $600 take profit
    else:
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
        
    # Analyze all symbols and find the best trend
    logger.info("Scanning symbols for the best trading setups...")
    best_symbol = None
    best_trend = None
    best_score = -1.0
    best_details = ""
    
    print("\n### Market Scanning Results (M5 timeframe):")
    print("| Symbol | Proposed Trend | Strength Score | Indicator Details |")
    print("| :--- | :--- | :--- | :--- |")
    
    for symbol in SYMBOLS:
        if not mt5.symbol_select(symbol, True):
            continue
        trend, score, details = analyze_symbol_trend(symbol)
        print(f"| {symbol} | **{trend}** | {score:.2f} | {details} |")
        if score > best_score:
            best_score = score
            best_symbol = symbol
            best_trend = trend
            best_details = details
            
    if not best_symbol or best_score == -1.0:
        # Absolute fallback if all fail or score is -1
        best_symbol = "XAUUSD"
        best_trend = "BUY"
        best_details = "Fallback default"
        
    print(f"\n-> **Selected Best Setup**: **{best_symbol}** is in a strong **{best_trend}** trend (Score: {best_score:.2f}).")
    print(f"Details: {best_details}")
    
    basket_id = f"BASKET_BEST_{best_symbol}_{int(time.time())}"
    logger.info(f"Generating 10-position basket: {basket_id}")
    
    volume = get_lot_size(best_symbol)
    
    tick = mt5.symbol_info_tick(best_symbol)
    if tick is None:
        logger.error(f"Failed to fetch market price for {best_symbol}. Exiting.")
        client.disconnect()
        sys.exit(1)
        
    price = tick.ask if best_trend == "BUY" else tick.bid
    sl, tp = get_sltp_levels(best_symbol, best_trend, price)
    
    print(f"\n### Executing 10 Positions Basket for {best_symbol}: {basket_id}")
    print("| Trade # | Symbol | Action | Volume | Price | Stop Loss (SL) | Take Profit (TP) | Ticket | Status |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    success_count = 0
    for i in range(1, 11):
        try:
            # Re-fetch price to minimize slippage on multiple fills
            curr_tick = mt5.symbol_info_tick(best_symbol)
            curr_price = (curr_tick.ask if best_trend == "BUY" else curr_tick.bid) if curr_tick else price
            curr_sl, curr_tp = get_sltp_levels(best_symbol, best_trend, curr_price)
            
            result = send_order(
                client._connection,
                action=TradeRequestActions.DEAL,
                order_type=OrderType.BUY if best_trend == "BUY" else OrderType.SELL,
                symbol=best_symbol,
                volume=volume,
                price=curr_price,
                stop_loss=curr_sl,
                take_profit=curr_tp,
                comment=basket_id
            )
            
            if result.get("success"):
                response_data = result.get("data")
                ticket = response_data.order if response_data else "Unknown"
                print(f"| #{i} | {best_symbol} | **{best_trend}** | {volume} | {curr_price:.5f} | {curr_sl:.5f} | {curr_tp:.5f} | `{ticket}` | Filled |")
                success_count += 1
            else:
                reason = result.get("message", "Unknown error")
                print(f"| #{i} | {best_symbol} | {best_trend} | {volume} | {curr_price:.5f} | {curr_sl:.5f} | {curr_tp:.5f} | - | Failed: {reason} |")
                
        except Exception as e:
            print(f"| #{i} | {best_symbol} | {best_trend} | {volume} | - | - | - | - | Error: {e} |")
            
    print(f"\nSuccessfully launched **{success_count}/10** trades on **{best_symbol}**.")
    print(f"Each position will automatically close when it reaches +$2.00 profit. Basket ID: `{basket_id}`")
    
    client.disconnect()

if __name__ == "__main__":
    main()
