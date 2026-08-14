import os
import sys
import time
import concurrent.futures
import logging
from datetime import datetime
import pandas as pd
import numpy as np
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(PROJECT_ROOT, ".agents"))
from metatrader_client import MT5Client
from metatrader_client.order.send_order import send_order
from metatrader_client.types import TradeRequestActions, OrderType
import MetaTrader5 as mt5

# Set up logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("alphaedge_trading.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("AlphaEdge")

def load_environment_file() -> None:
    """Load local KEY=VALUE settings without adding another dependency."""
    environment_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(environment_path):
        return

    with open(environment_path, encoding="utf-8") as environment_file:
        for line in environment_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_environment_file()

MT5_CONFIG = {
    "login": int(os.environ["MT5_LOGIN"]),
    "password": os.environ["MT5_PASSWORD"],
    "server": os.environ["MT5_SERVER"],
}

ASSET_CONFIG = {
    # Metals & Energies
    "XAUUSDm": {"strategies": ["core_system", "breakout"], "timeframes": [mt5.TIMEFRAME_M5, mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M30], "sessions": ["London", "NY"]},

    "USOILm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    
    # Indices
    "USTECm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "US30m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "SPX500m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "GER30m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},
    "UK100m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},

    # Crypto
    "BTCUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["24/7"]},
    "ETHUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["24/7"]},
    
    # Major Forex
    "EURUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},
    "GBPUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},
    "USDJPYm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London", "NY"]},
    "AUDUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London"]},
    "USDCADm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["NY"]},
    "NZDUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London"]},
    "USDCHFm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London", "NY"]},

    # Minor/Cross Forex
    "EURJPYm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London", "NY"]},
    "GBPJPYm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London", "NY"]},
    "EURGBPm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London"]},
    "EURAUDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London"]},
    "GBPAUDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London"]},
    "AUDJPYm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["London", "NY"]},
}
SYMBOLS = list(ASSET_CONFIG.keys())
MAX_DAILY_LOSS_USD = 50.0
DAILY_PROFIT_TARGET_USD = 500.0
PULLBACK_ATR_FRACTION = 0.5
PENDING_ORDER_EXPIRY_SECONDS = 7200

# Runtime configuration (override with .env)
MODE = os.getenv("AE_MODE", "M30_STRUCTURAL")  # or 'M5_FAST'
AE_LOT_MULTIPLIER = float(os.getenv("AE_LOT_MULTIPLIER", "1.0"))
AE_MAX_WORKERS = int(os.getenv("AE_MAX_WORKERS", "10"))
AE_RR_MIN = float(os.getenv("AE_RR_MIN", "2.0"))
AE_MAX_CONCURRENT_TRADES = int(os.getenv("AE_MAX_CONCURRENT_TRADES", "20"))
AE_PULLBACK_ATR_FRACTION = float(os.getenv("AE_PULLBACK_ATR_FRACTION", "0.5"))
AE_ATR_SL_MULTIPLIER = float(os.getenv("AE_ATR_SL_MULTIPLIER", "1.0"))
AE_TRAILING_ENABLE = os.getenv("AE_TRAILING_ENABLE", "1") == "1"
AE_TRAIL_PROFIT_ATR = float(os.getenv("AE_TRAIL_PROFIT_ATR", "1.0"))
AE_TRAIL_SL_MULT = float(os.getenv("AE_TRAIL_SL_MULT", "0.5"))
PROP_FIRM_MODE = os.getenv("PROP_FIRM_MODE", "0") == "1"
PROP_FIRM_DAILY_DD_LIMIT = float(os.getenv("PROP_FIRM_DAILY_DD_LIMIT", "-3.0"))
PROP_FIRM_MAX_OPEN_TRADES = int(os.getenv("PROP_FIRM_MAX_OPEN_TRADES", "4"))

# Optional fixed-point trailing stop (pips/points). If >0, overrides ATR-based trail.
AE_TRAIL_SL_PIPS = float(os.getenv("AE_TRAIL_SL_PIPS", "0"))

# Map mode to timeframe defaults
if MODE == "M5_FAST":
    MAIN_TIMEFRAME = mt5.TIMEFRAME_M5
    CONFIRM_TIMEFRAME = mt5.TIMEFRAME_M1
    # faster, looser defaults for higher frequency
    AE_PULLBACK_ATR_FRACTION = float(os.getenv("AE_PULLBACK_ATR_FRACTION", "0.3"))
    AE_ATR_SL_MULTIPLIER = float(os.getenv("AE_ATR_SL_MULTIPLIER", "0.8"))
    AE_RR_MIN = float(os.getenv("240", "1.5"))
else:
    MAIN_TIMEFRAME = mt5.TIMEFRAME_M30
    CONFIRM_TIMEFRAME = mt5.TIMEFRAME_M5
    AE_PULLBACK_ATR_FRACTION = float(os.getenv("AE_PULLBACK_ATR_FRACTION", "0.5"))
    AE_ATR_SL_MULTIPLIER = float(os.getenv("AE_ATR_SL_MULTIPLIER", "1.0"))
    AE_RR_MIN = float(os.getenv("AE_RR_MIN", "2.0"))

# Backwards-compatible names used later
PULLBACK_ATR_FRACTION = AE_PULLBACK_ATR_FRACTION
ATR_SL_MULTIPLIER = AE_ATR_SL_MULTIPLIER
RISK_REWARD_MIN = AE_RR_MIN
MAX_WORKERS = AE_MAX_WORKERS

from trading_bot_skills.indicators import (
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_ema,
    calculate_atr,
    find_support_resistance,
)
from trading_bot_skills.risk import assess_risk
from trading_bot_skills.token_stub import get_tradingagents_token
from trading_bot_skills.trade_config import TELEGRAM_ENABLED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_alert(message: str):
    if not TELEGRAM_ENABLED:
        return
    import urllib.request
    import urllib.parse
    import json
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

def get_lot_size(symbol: str, sl_price: float = 0.0, entry_price: float = 0.0) -> float:
    """Calculate lot size based on 0.5% dynamic risk using ATR-based stop loss distance."""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return 0.01
        
    vol_min = symbol_info.volume_min
    vol_max = symbol_info.volume_max
    vol_step = symbol_info.volume_step
    
    if sl_price == 0.0 or entry_price == 0.0:
        return max(vol_min, round(vol_min * AE_LOT_MULTIPLIER, 2))
        
    account = mt5.account_info()
    if not account:
        return vol_min
        
    balance = account.balance
    risk_percentage = 0.005 # 0.5% risk per trade
    risk_usd = balance * risk_percentage
    
    price_distance = abs(entry_price - sl_price)
    if price_distance == 0:
        return vol_min
        
    tick_size = symbol_info.trade_tick_size
    tick_value = symbol_info.trade_tick_value
    if tick_size == 0 or tick_value == 0:
        return vol_min
        
    ticks_at_risk = price_distance / tick_size
    loss_for_one_lot = ticks_at_risk * tick_value
    
    if loss_for_one_lot == 0:
        return vol_min
        
    optimal_volume = risk_usd / loss_for_one_lot
    
    if vol_step > 0:
        optimal_volume = round(optimal_volume / vol_step) * vol_step
        
    optimal_volume = max(vol_min, min(optimal_volume, vol_max))
    decimals = len(str(vol_step).split('.')[1]) if '.' in str(vol_step) else 0
    return round(optimal_volume, decimals)

# Simple test lot size that respects the instrument's minimum volume
def get_test_lot(symbol: str) -> float:
    """Return the minimum allowable volume for the symbol, suitable for test trades.
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.01
    return max(info.volume_min, 0.01)

# Simple trade logger to record trade details to a CSV file
def log_trade(symbol: str, action: str, price: float, sl: float, tp: float, quantity: float, comment: str = ""):
    """Append a trade record to 'trade_log.csv'."""
    import csv, os
    log_path = os.path.join(os.path.dirname(__file__), "trade_log.csv")
    file_exists = os.path.isfile(log_path)
    fields = ["timestamp", "symbol", "action", "price", "sl", "tp", "quantity", "comment"]
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "price": price,
            "sl": sl,
            "tp": tp,
            "quantity": quantity,
            "comment": comment,
        })


def analyze_liquidity_reversion_df(df: pd.DataFrame, symbol: str | None = None):
    """Liquidity sweep mean-reversion entry logic."""
    if df is None or len(df) < 70:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data"

    df = df.copy()
    df = calculate_bollinger_bands(df)
    df = calculate_rsi(df)
    df = calculate_atr(df)
    df['ema8'] = calculate_ema(df, 8)
    df['ema21'] = calculate_ema(df, 21)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prior_swing = df.iloc[-50:-10] if len(df) >= 60 else df.iloc[:-10]
    if len(prior_swing) < 20:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Not enough swing history"

    swing_low = prior_swing['low'].min()
    swing_high = prior_swing['high'].max()
    bb_mid = last['bb_mid']
    bb_lower = last['bb_lower']
    bb_upper = last['bb_upper']
    last_atr = last['atr']
    last_close = last['close']
    last_open = last['open']
    last_high = last['high']
    last_low = last['low']
    last_rsi = last['rsi']
    last_ema8 = last['ema8']
    last_ema21 = last['ema21']

    bullish_rejection = last_close > last_open and prev['close'] < prev['open']
    bearish_rejection = last_close < last_open and prev['close'] > prev['open']

    body_size = abs(last_close - last_open)
    lower_wick = min(last_close, last_open) - last_low
    upper_wick = last_high - max(last_close, last_open)

    sweep_buy = (
        last_low < swing_low - (0.18 * last_atr)
        and last_close > swing_low
        and bullish_rejection
        and last_rsi <= 40
        and lower_wick > body_size
    )
    sweep_sell = (
        last_high > swing_high + (0.18 * last_atr)
        and last_close < swing_high
        and bearish_rejection
        and last_rsi >= 60
        and upper_wick > body_size
    )

    ema_buy_ok = last_ema8 <= last_ema21
    ema_sell_ok = last_ema8 >= last_ema21

    h1_buy_ok = True
    h1_sell_ok = True
    h1_status = "H1 unchecked"
    if symbol is not None:
        h1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
        if h1_rates is not None and len(h1_rates) >= 20:
            df_h1 = pd.DataFrame(h1_rates)
            df_h1['sma20'] = df_h1['close'].rolling(window=20).mean()
            df_h1 = calculate_rsi(df_h1)
            last_h1_close = df_h1['close'].iloc[-1]
            last_h1_sma20 = df_h1['sma20'].iloc[-1]
            last_h1_rsi = df_h1['rsi'].iloc[-1]
            if last_h1_close < last_h1_sma20 and last_h1_rsi < 45:
                h1_buy_ok = False
                h1_status = f"H1 bear continuation ({last_h1_rsi:.1f})"
            elif last_h1_close > last_h1_sma20 and last_h1_rsi > 55:
                h1_sell_ok = False
                h1_status = f"H1 bull continuation ({last_h1_rsi:.1f})"
            else:
                h1_status = f"H1 friendly ({last_h1_rsi:.1f})"

    action = "NEUTRAL"
    sl = 0.0
    tp = 0.0
    entry_price = last_close
    details = f"RSI {last_rsi:.1f} | EMA8/21 {last_ema8:.5f}/{last_ema21:.5f} | H1 {h1_status}"

    # Aggressive live trading fallback: open only on truly extreme Bollinger/RSI conditions with trend alignment
    buy_pullback = last_close <= bb_lower and last_rsi <= 30
    sell_pullback = last_close >= bb_upper and last_rsi >= 70
    basic_buy = buy_pullback and last_ema8 <= last_ema21
    basic_sell = sell_pullback and last_ema8 >= last_ema21
    rr_threshold = 2.0

    if sweep_buy and ema_buy_ok and h1_buy_ok:
        sl = min(last_low, swing_low) - (3.5 * last_atr)
        tp = max(bb_mid, last_close + max(2.5 * last_atr, 0.6 * (swing_high - last_close)))
        sl, tp = assess_risk("BUY", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = entry_price - sl
        reward = tp - entry_price
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "BUY"
            details = f"Liquidity sweep BUY. Sweep low {swing_low:.5f}. RSI {last_rsi:.1f}. H1 {h1_status}. R:R {reward/risk:.2f}"
        else:
            details = f"BUY sweep rejected by R:R ({reward/risk:.2f})."

    elif basic_buy and h1_buy_ok:
        sl = last_low - (3.5 * last_atr)
        tp = last_close + max(2.5 * last_atr, bb_mid - last_close, 0.6 * (swing_high - last_close))
        sl, tp = assess_risk("BUY", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = entry_price - sl
        reward = tp - entry_price
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "BUY"
            details = f"Aggressive BUY. Close {last_close:.5f} below BB lower {bb_lower:.5f} or RSI {last_rsi:.1f}. H1 {h1_status}. R:R {reward/risk:.2f}"
        else:
            details = f"Aggressive BUY rejected by R:R ({reward/risk:.2f})."

    elif sweep_sell and ema_sell_ok and h1_sell_ok:
        sl = max(last_high, swing_high) + (3.5 * last_atr)
        tp = min(bb_mid, last_close - max(2.5 * last_atr, 0.6 * (last_close - swing_low)))
        sl, tp = assess_risk("SELL", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = sl - entry_price
        reward = entry_price - tp
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "SELL"
            details = f"Liquidity sweep SELL. Sweep high {swing_high:.5f}. RSI {last_rsi:.1f}. H1 {h1_status}. R:R {reward/risk:.2f}"
        else:
            details = f"SELL sweep rejected by R:R ({reward/risk:.2f})."

    elif basic_sell and h1_sell_ok:
        sl = last_high + (3.5 * last_atr)
        tp = last_close - max(2.5 * last_atr, last_close - bb_mid, 0.6 * (last_close - swing_low))
        sl, tp = assess_risk("SELL", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = sl - entry_price
        reward = entry_price - tp
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "SELL"
            details = f"Aggressive SELL. Close {last_close:.5f} above BB upper {bb_upper:.5f} or RSI {last_rsi:.1f}. H1 {h1_status}. R:R {reward/risk:.2f}"
        else:
            details = f"Aggressive SELL rejected by R:R ({reward/risk:.2f})."

    else:
        details = f"No sweep setup. RSI {last_rsi:.1f}. EMA8/21 {last_ema8:.5f}/{last_ema21:.5f}."

    return action, sl, tp, entry_price, details


def analyze_core_system_df(df: pd.DataFrame, symbol: str):
    if len(df) < 200:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data for EMA200"
        
    df = df.copy()
    df['ema50'] = calculate_ema(df, 50)
    df['ema200'] = calculate_ema(df, 200)
    df = calculate_atr(df)
    last = df.iloc[-1]
    
    bias = "BULLISH" if last['ema50'] > last['ema200'] else "BEARISH"
    
    pdh, pdl = 0.0, float('inf')
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 2)
    if rates_d1 is not None and len(rates_d1) > 0:
        yesterday = rates_d1[0]
        pdh = yesterday['high']
        pdl = yesterday['low']
        
    recent = df.iloc[-15:]
    sweep_high = recent['high'].max()
    sweep_low = recent['low'].min()
    
    last_close = last['close']
    last_open = last['open']
    last_high = last['high']
    last_low = last['low']
    last_atr = last['atr']
    
    body_size = abs(last_close - last_open)
    lower_wick = min(last_close, last_open) - last_low
    upper_wick = last_high - max(last_close, last_open)
    
    if bias == "BEARISH" and sweep_high >= pdh and pdh > 0:
        if last_close > last['ema50'] and last_close < sweep_high and upper_wick > body_size:
            sl = sweep_high + (3.5 * last_atr)
            tp = last_close - 2.0 * (sl - last_close)
            sl, tp = assess_risk("SELL", sl, tp, last_close, last_atr, "neutral")
            return "SELL", sl, tp, last_close, f"Core System: PDH Sweep & Wick Rejection. UW={upper_wick:.5f} > Body={body_size:.5f}"
            
    if bias == "BULLISH" and sweep_low <= pdl and pdl < float('inf'):
        if last_close < last['ema50'] and last_close > sweep_low and lower_wick > body_size:
            sl = sweep_low - (3.5 * last_atr)
            tp = last_close + 2.0 * (last_close - sl)
            sl, tp = assess_risk("BUY", sl, tp, last_close, last_atr, "neutral")
            return "BUY", sl, tp, last_close, f"Core System: PDL Sweep & Wick Rejection. LW={lower_wick:.5f} > Body={body_size:.5f}"
            
    return "NEUTRAL", 0.0, 0.0, 0.0, f"No core setup. Bias: {bias}, PDH: {pdh:.5f}, PDL: {pdl:.5f}"

def analyze_breakout_df(df: pd.DataFrame, symbol: str):
    """Volatility expansion breakout strategy."""
    if len(df) < 50:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data"
    df = df.copy()
    df = calculate_bollinger_bands(df)
    df = calculate_atr(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    last_close = last['close']
    last_atr = last['atr']
    
    if last_close > last['bb_upper'] and prev['close'] <= prev['bb_upper']:
        sl = last['bb_mid'] - (0.5 * last_atr)
        tp = last_close + 2.0 * (last_close - sl)
        sl, tp = assess_risk("BUY", sl, tp, last_close, last_atr, "neutral")
        return "BUY", sl, tp, last_close, f"Breakout BUY. Close above BB_upper."
        
    if last_close < last['bb_lower'] and prev['close'] >= prev['bb_lower']:
        sl = last['bb_mid'] + (0.5 * last_atr)
        tp = last_close - 2.0 * (sl - last_close)
        sl, tp = assess_risk("SELL", sl, tp, last_close, last_atr, "neutral")
        return "SELL", sl, tp, last_close, f"Breakout SELL. Close below BB_lower."
        
    return "NEUTRAL", 0.0, 0.0, 0.0, "No breakout."

def analyze_strategies(symbol: str):
    config = ASSET_CONFIG.get(symbol, {"strategies": ["liquidity_sweep"], "timeframes": [MAIN_TIMEFRAME]})
    strategies = config["strategies"]
    timeframes = config["timeframes"]
    
    best_action = "NEUTRAL"
    best_result = ("NEUTRAL", 0.0, 0.0, 0.0, "No setup found across any strategy or timeframe", "NONE")
    
    try:
        for tf in timeframes:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, 250)
            if rates is None or len(rates) < 70:
                continue
            df = pd.DataFrame(rates)
            
            for strategy in strategies:
                if strategy == "core_system":
                    res = analyze_core_system_df(df, symbol)
                elif strategy == "liquidity_sweep":
                    res = analyze_liquidity_reversion_df(df, symbol)
                elif strategy in ["breakout", "breakout_retest"]:
                    res = analyze_breakout_df(df, symbol)
                elif strategy in ["trend_continuation", "trend_pullback"]:
                    res = analyze_trend_pullback_df(df, symbol)
                elif strategy == "opening_range":
                    res = analyze_opening_range_df(df, symbol)
                else:
                    res = ("NEUTRAL", 0.0, 0.0, 0.0, f"Unknown strategy: {strategy}")
                
                action, sl, tp, ep, details = res
                if action in ["BUY", "SELL"]:
                    details = f"[{strategy.upper()} on {tf}] " + details
                    return action, sl, tp, ep, details, strategy.upper()
                    
        return best_result
    except Exception as e:
        logger.error(f"Failed to analyze structural edge for {symbol}: {e}")
        return "NEUTRAL", 0.0, 0.0, 0.0, f"Error: {e}", "NONE"
def run_alphaedge(execute_orders: bool = False, approved_symbols: set[str] | None = None):
    client = MT5Client(MT5_CONFIG)
    try:
        client.connect()
        logger.info("AlphaEdge Strategy initialized.")
    except Exception as e:
        logger.error(f"MT5 connection failed: {e}")
        raise RuntimeError(f"MT5 connection failed: {e}")
        
    # 1. Calculate Daily Profit (For Logging Only - No Limits)
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    deals = mt5.history_deals_get(today_start, now)
    daily_profit = 0.0
    bot_tags = ["ALPHAEDGE_TRADE", "CORE_SYSTEM", "LIQUIDITY_SWEEP", "BREAKOUT"]
    if deals:
        df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        our_pos_ids = df_deals[df_deals['comment'].isin(bot_tags) & (df_deals['entry'] == 0)]['position_id'].unique()
        exits_today = df_deals[df_deals['entry'].isin([1, 3]) & df_deals['position_id'].isin(our_pos_ids)]
        if not exits_today.empty:
            daily_profit = exits_today['profit'].sum() + exits_today['commission'].sum() + exits_today['swap'].sum()
            
    # Prop Firm Daily DD Check
    account = mt5.account_info()
    prop_firm_locked = False
    if PROP_FIRM_MODE and account:
        floating_profit = sum(p.profit for p in (mt5.positions_get() or []) if getattr(p, 'comment', '') in bot_tags)
        total_daily_pnl = daily_profit + floating_profit
        start_balance = account.balance - daily_profit
        dd_percent = (total_daily_pnl / start_balance) * 100 if start_balance > 0 else 0.0
        logger.info(f"[Prop Firm] Current Daily Net P&L: ${total_daily_pnl:+.2f} ({dd_percent:+.2f}%) | Limit: {PROP_FIRM_DAILY_DD_LIMIT}%")
        
        if dd_percent <= PROP_FIRM_DAILY_DD_LIMIT:
            logger.warning(f"🚨 PROP FIRM LOCKDOWN: Daily Drawdown ({dd_percent:.2f}%) hit the kill switch limit ({PROP_FIRM_DAILY_DD_LIMIT}%). Bot is suspending new trades until tomorrow.")
            prop_firm_locked = True
    else:
        logger.info(f"Current Daily Net P&L: ${daily_profit:+.2f} (Trading Uncapped)")

    # 2. Manage Breakeven for Active Positions
    open_positions = mt5.positions_get()
    if execute_orders and open_positions:
        for pos in open_positions:
            if getattr(pos, 'comment', '') == "ALPHAEDGE_TRADE":
                symbol = pos.symbol
                # use main timeframe to estimate ATR for trailing/lock adjustments
                rates = mt5.copy_rates_from_pos(symbol, MAIN_TIMEFRAME, 0, 20)
                if rates is not None and len(rates) >= 14:
                    df_rates = pd.DataFrame(rates)
                    df_rates = calculate_atr(df_rates)
                    atr = df_rates['atr'].iloc[-1]

                    # 2-Stage Trailing / lock-in logic
                    try:
                        is_stage1 = False
                        is_stage2 = False
                        if pos.type == mt5.ORDER_TYPE_BUY:
                            if pos.price_current >= (pos.price_open + 2.0 * atr):
                                is_stage2 = True
                            elif pos.price_current >= (pos.price_open + 1.0 * atr):
                                is_stage1 = True
                        elif pos.type == mt5.ORDER_TYPE_SELL:
                            if pos.price_current <= (pos.price_open - 2.0 * atr):
                                is_stage2 = True
                            elif pos.price_current <= (pos.price_open - 1.0 * atr):
                                is_stage1 = True

                        if (is_stage1 or is_stage2) and AE_TRAILING_ENABLE:
                            if pos.type == mt5.ORDER_TYPE_BUY:
                                if is_stage2:
                                    new_sl = round(pos.price_current - (1.0 * atr), 5)
                                    stage_name = "Stage 2 Trail (1 ATR)"
                                else:
                                    # Breakeven + small buffer
                                    new_sl = round(pos.price_open + (0.1 * atr), 5)
                                    stage_name = "Stage 1 Breakeven Lock"
                                
                                # ensure we only move SL forward
                                if pos.sl == 0 or new_sl > pos.sl:
                                    request = {
                                        "action": mt5.TRADE_ACTION_SLTP,
                                        "position": pos.ticket,
                                        "symbol": pos.symbol,
                                        "sl": new_sl,
                                        "tp": pos.tp
                                    }
                                    res = mt5.order_send(request)
                                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                        msg = f"🔒 <b>[AlphaEdge SL Adjusted]</b>\nSymbol: {symbol}\nAction: Moved SL to {new_sl} ({stage_name})"
                                        logger.info(f"Moved SL to {new_sl} for {symbol} ({stage_name})")
                                        send_telegram_alert(msg)
                                    else:
                                        logger.error(f"Failed to adjust SL for {symbol}: {getattr(res,'retcode', res) if res else mt5.last_error()}")
                            else:
                                if is_stage2:
                                    new_sl = round(pos.price_current + (1.0 * atr), 5)
                                    stage_name = "Stage 2 Trail (1 ATR)"
                                else:
                                    new_sl = round(pos.price_open - (0.1 * atr), 5)
                                    stage_name = "Stage 1 Breakeven Lock"
                                
                                if pos.sl == 0 or new_sl < pos.sl:
                                    request = {
                                        "action": mt5.TRADE_ACTION_SLTP,
                                        "position": pos.ticket,
                                        "symbol": pos.symbol,
                                        "sl": new_sl,
                                        "tp": pos.tp
                                    }
                                    res = mt5.order_send(request)
                                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                        msg = f"🔒 <b>[AlphaEdge SL Adjusted]</b>\nSymbol: {symbol}\nAction: Moved SL to {new_sl} ({stage_name})"
                                        logger.info(f"Moved SL to {new_sl} for {symbol} ({stage_name})")
                                        send_telegram_alert(msg)
                                    else:
                                        logger.error(f"Failed to adjust SL for {symbol}: {getattr(res,'retcode', res) if res else mt5.last_error()}")
                    except Exception as e:
                        logger.error(f"Trailing SL adjustment failure for {symbol}: {e}")

    current_day = datetime.utcnow().weekday()
    current_hour = datetime.utcnow().hour
    
    is_weekend = current_day in [5, 6]
    friday_block = current_day == 4 and current_hour >= 21
    
    if PROP_FIRM_MODE and (prop_firm_locked or friday_block):
        if prop_firm_locked:
            logger.info("-> 🚨 Prop Firm Daily Drawdown Kill Switch Active. Scanning disabled.")
        elif friday_block:
            logger.info("-> 🚫 Friday Weekend Block Active (Post 21:00 UTC). Scanning disabled.")
        client.disconnect()
        return []
    
    current_hour = datetime.utcnow().hour
    active_sessions = ["24/7"]
    if 7 <= current_hour < 16:
        active_sessions.append("London")
    if 13 <= current_hour < 22:
        active_sessions.append("NY")
        
    session_symbols = []
    for sym, config in ASSET_CONFIG.items():
        if any(s in active_sessions for s in config.get("sessions", [])):
            session_symbols.append(sym)
    
    if is_weekend:
        # Scan only major crypto symbols on weekends
        active_symbols = [s.name for s in mt5.symbols_get() if s.visible and s.name in session_symbols and ("BTC" in s.name or "ETH" in s.name)]
        logger.info(f"[Weekend Mode] Scanning Crypto only: {active_symbols}")
    else:
        # Scan symbols that are in our custom SYMBOLS list AND currently in an active session
        active_symbols = [s.name for s in mt5.symbols_get() if s.visible and s.name in session_symbols]
        logger.info(f"[Weekday Mode] Active Sessions: {active_sessions}. Scanning symbols: {active_symbols}")

    logger.info("=== -> AlphaEdge Liquidity Sweep / Mean Reversion Scan (M30 Timeframe) ===")
    logger.info("| Symbol | Setup | Price | Stop Loss | Take Profit | R:R | Analysis Details |")
    logger.info("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    scan_results = {}
    
    def scan_symbol(symbol):
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info or not symbol_info.visible:
            return symbol, ("NEUTRAL", 0.0, 0.0, 0.0, "Symbol not available/visible", "NONE")
        try:
            res = analyze_strategies(symbol)
            return symbol, res
        except Exception as e:
            return symbol, ("NEUTRAL", 0.0, 0.0, 0.0, f"Error: {e}", "NONE")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_symbol, s): s for s in active_symbols}
        for future in concurrent.futures.as_completed(futures):
            symbol, (action, sl, tp, entry_price, details, strategy) = future.result()
            scan_results[symbol] = {
                "action": action,
                "sl": sl,
                "tp": tp,
                "entry_price": entry_price,
                "details": details,
                "strategy": strategy
            }
        

                
    # --- Autonomous trading: place orders only when the structural edge strategy signals BUY or SELL ---
    triggers = []
    for symbol, result in scan_results.items():
        action = result["action"]
        if action not in ["BUY", "SELL"]:
            continue
        sl = result["sl"]
        tp = result["tp"]
        entry_price = result["entry_price"]
        strategy = result["strategy"]
        logger.info(f"Strategy {strategy} signals {action} for {symbol} at {entry_price:.5f} (SL={sl:.5f}, TP={tp:.5f})")
        triggers.append((symbol, action, sl, tp, entry_price, result["details"], strategy))

    if not triggers:
        logger.info("-> No liquidity sweep setups confirmed for entry. Waiting for price to trigger mean-reversion extremes.")
        client.disconnect()
        return []

    if not execute_orders:
        logger.info("=== -> Approval Required: no orders submitted ===")
        for symbol, action, sl, tp, entry_price, details, strategy in triggers:
            logger.info(f"PENDING | {symbol} | {action} | Entry {entry_price:.5f} | SL {sl:.5f} | TP {tp:.5f} | Strategy: {strategy}")
        client.disconnect()
        return triggers

    logger.info("=== -> Executing Structural Edge Orders ===")
    open_positions = mt5.positions_get()
    active_trades = []
    if open_positions:
        active_trades = [(pos.symbol, getattr(pos, 'comment', '')) for pos in open_positions]
    pending_orders = mt5.orders_get() or []
    active_trades.extend([(order.symbol, getattr(order, 'comment', '')) for order in pending_orders])

    for symbol, action, sl, tp, entry_price, details, strategy_name in triggers:
        if approved_symbols is not None and symbol not in approved_symbols:
            logger.info(f"Skipping {symbol}: not in the approved symbol list.")
            continue
            
        # Max Concurrent Risk Prop Firm Limit
        if PROP_FIRM_MODE and len(active_trades) >= PROP_FIRM_MAX_OPEN_TRADES:
            logger.info(f"Skipping {symbol}: Max Open Trades Limit ({PROP_FIRM_MAX_OPEN_TRADES}) reached. Protecting account equity.")
            continue
            
        # Prevent duplicate trades: skip if THIS specific strategy already has a trade open on this symbol
        if (symbol, strategy_name) in active_trades:
            logger.info(f"Skipping {symbol}: {strategy_name} trade already active on this symbol.")
            continue
            
        volume = get_lot_size(symbol, sl, entry_price)
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        try:
            # Get current market price for the order
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error(f"Cannot get tick for {symbol}, skipping.")
                continue
            price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "deviation": 20,
                "comment": strategy_name,
                "type_filling": mt5.ORDER_FILLING_FOK,
                "type_time": mt5.ORDER_TIME_GTC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                ticket = result.order
                logger.info(f"Successfully opened {action} market trade on {symbol} (Ticket: {ticket}, SL: {sl:.5f}, TP: {tp:.5f})")
                msg = f"🚀 <b>[AlphaEdge Market Trade Opened]</b>\nStrategy: {strategy_name}\nSymbol: {symbol}\nAction: {action}\nConfirmation: {details}\nLot Size: {volume}\nSL: {sl:.5f}\nTP: {tp:.5f}"
                send_telegram_alert(msg)
                try:
                    log_trade(symbol, action, entry_price, sl, tp, volume, strategy_name)
                except Exception as log_err:
                    logger.error(f"Failed to log trade for {symbol}: {log_err}")
            else:
                logger.error(f"Failed to place {action} market order on {symbol}: {getattr(result, 'comment', mt5.last_error())}")
        except Exception as e:
            logger.error(f"Order send error on {symbol}: {e}")
            
    client.disconnect()

if __name__ == "__main__":
    run_alphaedge()
