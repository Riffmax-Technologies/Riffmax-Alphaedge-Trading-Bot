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
from prop_firm_config import PropFirmEngine

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

PROP_FIRM_STARTING_BALANCE = 15000.0  # Default — overridden by .env
if "PROP_FIRM_STARTING_BALANCE" in os.environ:
    PROP_FIRM_STARTING_BALANCE = float(os.environ["PROP_FIRM_STARTING_BALANCE"])

ASSET_CONFIG = {
    # Metals & Energies — Gold uses dedicated gold_system strategy
    "XAUUSDm": {"strategies": ["gold_system", "core_system"], "timeframes": [mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M30], "sessions": ["London", "NY"]},

    "USOILm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    
    # Indices
    "USTECm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "US30m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "SPX500m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["NY"]},
    "GER30m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},
    "UK100m": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M5], "sessions": ["London"]},

    # Crypto (BTC only — ETH removed per user decision)
    "BTCUSDm": {"strategies": ["core_system", "liquidity_sweep"], "timeframes": [mt5.TIMEFRAME_M15], "sessions": ["24/7"]},
    
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
PROP_FIRM_MODE = True  # Always ON for Prop Firm Challenge account
PROP_FIRM_DAILY_DD_LIMIT = -3.0   # 3% daily loss limit
PROP_FIRM_MAX_OPEN_TRADES = 4     # Max 4 concurrent trades

# Optional fixed-point trailing stop (pips/points). If >0, overrides ATR-based trail.
AE_TRAIL_SL_PIPS = float(os.getenv("AE_TRAIL_SL_PIPS", "0"))

# Map mode to timeframe defaults
if MODE == "M5_FAST":
    MAIN_TIMEFRAME = mt5.TIMEFRAME_M5
    CONFIRM_TIMEFRAME = mt5.TIMEFRAME_M1
    # faster, looser defaults for higher frequency
    AE_PULLBACK_ATR_FRACTION = float(os.getenv("AE_PULLBACK_ATR_FRACTION", "0.3"))
    AE_ATR_SL_MULTIPLIER = float(os.getenv("AE_ATR_SL_MULTIPLIER", "0.8"))
    AE_RR_MIN = float(os.getenv("AE_RR_MIN", "1.5"))
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



def get_h4_bias(symbol: str) -> str:
    """
    Get the true structural market bias from the H4 timeframe.
    H4 EMA50 above H4 EMA200 = institutional BULLISH trend.
    H4 EMA50 below H4 EMA200 = institutional BEARISH trend.
    This prevents taking counter-trend trades on lower timeframes.
    """
    rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 210)
    if rates_h4 is None or len(rates_h4) < 200:
        return "NEUTRAL"
    df_h4 = pd.DataFrame(rates_h4)
    df_h4['ema50'] = calculate_ema(df_h4, 50)
    df_h4['ema200'] = calculate_ema(df_h4, 200)
    last_h4 = df_h4.iloc[-1]
    if last_h4['ema50'] > last_h4['ema200']:
        return "BULLISH"
    elif last_h4['ema50'] < last_h4['ema200']:
        return "BEARISH"
    return "NEUTRAL"


def get_asian_range(symbol: str):
    """
    Get the Asian session high and low (02:00 - 08:00 UTC).
    Used as a high-probability liquidity pool filter for Forex.
    Returns (asian_high, asian_low) or (None, None) if unavailable.
    """
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    # Get M30 candles for the last 48 hours (enough to always capture an Asian session)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 100)
    if rates is None or len(rates) < 16:
        return None, None
    df_a = pd.DataFrame(rates)
    df_a['time'] = pd.to_datetime(df_a['time'], unit='s', utc=True)
    # Find the most recent Asian session (02:00 - 08:00 UTC today or yesterday)
    for days_back in [0, 1]:
        target_date = (now_utc - pd.Timedelta(days=days_back)).date()
        session = df_a[
            (df_a['time'].dt.date == target_date) &
            (df_a['time'].dt.hour >= 2) &
            (df_a['time'].dt.hour < 8)
        ]
        if len(session) >= 4:
            return session['high'].max(), session['low'].min()
    return None, None

def analyze_liquidity_reversion_df(df: pd.DataFrame, symbol: str | None = None):
    """
    Upgraded Liquidity Sweep Strategy.
    Improvements:
    1. H4 structural bias — only trade WITH the dominant trend.
    2. Volume filter — rejection candle must have above-average institutional volume.
    3. Asian Range filter — prioritise sweeps that also take out the Asian session range.
    4. Institutional SL — placed just beyond the wick low/high, not 3.5 ATR away.
    5. Removed dangerous BB/RSI fallback entries.
    """
    if df is None or len(df) < 70:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data"

    df = df.copy()
    df = calculate_bollinger_bands(df)
    df = calculate_rsi(df)
    df = calculate_atr(df)
    df['ema21'] = calculate_ema(df, 21)

    last = df.iloc[-1]   # Live candle — entry price, ATR
    prev = df.iloc[-2]   # Last CLOSED candle — all geometry

    prior_swing = df.iloc[-50:-5] if len(df) >= 55 else df.iloc[:-5]
    if len(prior_swing) < 20:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Not enough swing history"

    swing_low  = prior_swing['low'].min()
    swing_high = prior_swing['high'].max()

    last_atr   = last['atr']
    last_close = last['close']
    last_rsi   = last['rsi']
    last_ema21 = last['ema21']
    bb_mid     = last['bb_mid']

    # --- Closed candle geometry ---
    prev_close = prev['close']
    prev_open  = prev['open']
    prev_high  = prev['high']
    prev_low   = prev['low']
    prev_rsi   = prev['rsi']
    prev_vol   = prev['tick_volume']

    body_size  = abs(prev_close - prev_open)
    lower_wick = min(prev_close, prev_open) - prev_low
    upper_wick = prev_high - max(prev_close, prev_open)

    # --- UPGRADE 1: H4 Structural Bias ---
    h4_bias = "NEUTRAL"
    if symbol:
        h4_bias = get_h4_bias(symbol)
    bias_ok_buy  = h4_bias in ["BULLISH", "NEUTRAL"]
    bias_ok_sell = h4_bias in ["BEARISH", "NEUTRAL"]

    # --- UPGRADE 2: Volume Filter ---
    avg_vol = df['tick_volume'].iloc[-21:-1].mean() if len(df) >= 21 else df['tick_volume'].mean()
    volume_confirmed = prev_vol >= 1.2 * avg_vol  # Rejection candle had institutional participation

    # --- UPGRADE 3: Asian Range Confluence ---
    asian_high, asian_low = None, None
    asian_sweep_buy  = False
    asian_sweep_sell = False
    if symbol:
        asian_high, asian_low = get_asian_range(symbol)
        if asian_high and asian_low:
            asian_sweep_buy  = prev_low < asian_low   # Swept below Asian low
            asian_sweep_sell = prev_high > asian_high  # Swept above Asian high

    # Core sweep conditions (closed candle only)
    bullish_rejection = prev_close > prev_open
    bearish_rejection = prev_close < prev_open

    sweep_buy = (
        prev_low < swing_low - (0.15 * last_atr)
        and prev_close > swing_low
        and bullish_rejection
        and prev_rsi <= 45
        and lower_wick > body_size
        and lower_wick > (0.4 * last_atr)
        and volume_confirmed
        and bias_ok_buy
    )
    sweep_sell = (
        prev_high > swing_high + (0.15 * last_atr)
        and prev_close < swing_high
        and bearish_rejection
        and prev_rsi >= 55
        and upper_wick > body_size
        and upper_wick > (0.4 * last_atr)
        and volume_confirmed
        and bias_ok_sell
    )

    # Boost R:R requirement if no Asian range confluence
    rr_threshold = 2.0 if (asian_sweep_buy or asian_sweep_sell) else 2.5

    action = "NEUTRAL"
    sl = 0.0
    tp = 0.0
    entry_price = last_close
    details = f"H4:{h4_bias} | RSI:{last_rsi:.1f} | Vol:{'OK' if volume_confirmed else 'LOW'} | Asian:{'HIT' if (asian_sweep_buy or asian_sweep_sell) else 'MISS'}"

    if sweep_buy:
        # UPGRADE 4: Institutional SL — just below the wick, not 3.5 ATR away
        sl = prev_low - (0.3 * last_atr)
        tp = last_close + max(2.5 * (last_close - sl), bb_mid - last_close, 0.6 * (swing_high - last_close))
        sl, tp = assess_risk("BUY", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = entry_price - sl
        reward = tp - entry_price
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "BUY"
            asian_note = " + Asian range" if asian_sweep_buy else ""
            details = f"Liq Sweep BUY{asian_note}. H4:{h4_bias}. SL below wick {prev_low:.5f}. RSI:{prev_rsi:.1f}. Vol:OK. R:R {reward/risk:.2f}"
        else:
            details = f"BUY sweep valid but R:R insufficient ({reward/risk:.2f} < {rr_threshold})."

    elif sweep_sell:
        # UPGRADE 4: Institutional SL — just above the wick
        sl = prev_high + (0.3 * last_atr)
        tp = last_close - max(2.5 * (sl - last_close), last_close - bb_mid, 0.6 * (last_close - swing_low))
        sl, tp = assess_risk("SELL", sl, tp, entry_price, last_atr, risk_level="neutral")
        risk = sl - entry_price
        reward = entry_price - tp
        if risk > 0 and reward > 0 and (reward / risk) >= rr_threshold:
            action = "SELL"
            asian_note = " + Asian range" if asian_sweep_sell else ""
            details = f"Liq Sweep SELL{asian_note}. H4:{h4_bias}. SL above wick {prev_high:.5f}. RSI:{prev_rsi:.1f}. Vol:OK. R:R {reward/risk:.2f}"
        else:
            details = f"SELL sweep valid but R:R insufficient ({reward/risk:.2f} < {rr_threshold})."

    return action, sl, tp, entry_price, details


def analyze_core_system_df(df: pd.DataFrame, symbol: str):
    """
    Upgraded Core System: PDH/PDL Liquidity Sweep + Wick Rejection.
    Improvements:
    1. H4 bias replaces M15 EMA50/200 — no more counter-trend trades.
    2. Volume filter — wick rejection must have institutional volume behind it.
    3. Institutional SL — placed just beyond the wick extreme, not 3.5 ATR away.
    4. Also checks Previous Week High/Low as secondary confluence.
    """
    if len(df) < 50:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data"
        
    df = df.copy()
    df = calculate_atr(df)
    df = calculate_rsi(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]   # Last CLOSED candle for all geometry
    
    last_close = last['close']
    last_atr   = last['atr']

    # --- UPGRADE 1: H4 Structural Bias ---
    h4_bias = get_h4_bias(symbol)
    if h4_bias == "NEUTRAL":
        return "NEUTRAL", 0.0, 0.0, 0.0, "H4 bias is NEUTRAL — no clear institutional trend"

    # --- Previous Day High/Low ---
    pdh, pdl = 0.0, float('inf')
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 3)
    if rates_d1 is not None and len(rates_d1) >= 1:
        pdh = rates_d1[0]['high']
        pdl = rates_d1[0]['low']

    # --- Previous Week High/Low (secondary confluence) ---
    pwh, pwl = 0.0, float('inf')
    rates_w1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 1, 2)
    if rates_w1 is not None and len(rates_w1) >= 1:
        pwh = rates_w1[0]['high']
        pwl = rates_w1[0]['low']

    # Most recent swing across last 20 candles
    recent = df.iloc[-20:]
    sweep_high = recent['high'].max()
    sweep_low  = recent['low'].min()

    # --- Closed candle geometry ---
    prev_close = prev['close']
    prev_open  = prev['open']
    prev_high  = prev['high']
    prev_low   = prev['low']
    prev_vol   = prev['tick_volume']

    body_size  = abs(prev_close - prev_open)
    lower_wick = min(prev_close, prev_open) - prev_low
    upper_wick = prev_high - max(prev_close, prev_open)

    # --- UPGRADE 2: Volume Filter ---
    avg_vol = df['tick_volume'].iloc[-21:-1].mean() if len(df) >= 21 else df['tick_volume'].mean()
    volume_confirmed = prev_vol >= 1.2 * avg_vol

    # Bearish: price swept PDH (or PWH) and closed back below with a clear upper wick
    if h4_bias == "BEARISH" and pdh > 0:
        pdhits_pdh = sweep_high >= pdh
        hits_pwh   = pwh > 0 and sweep_high >= pwh
        level_hit  = pdhits_pdh or hits_pwh
        level_name = "PDH" if pdhits_pdh else "PWH"
        level_val  = pdh if pdhits_pdh else pwh

        if level_hit:
            wick_valid = (
                prev_close < sweep_high
                and prev_close < prev_open        # bearish closed candle
                and upper_wick > body_size
                and upper_wick > (0.4 * last_atr)
                and volume_confirmed
            )
            if wick_valid:
                # UPGRADE 3: Institutional SL just above wick high
                sl = prev_high + (0.3 * last_atr)
                tp = last_close - 2.5 * (sl - last_close)
                sl, tp = assess_risk("SELL", sl, tp, last_close, last_atr, "neutral")
                risk = sl - last_close
                reward = last_close - tp
                if risk > 0 and reward > 0 and (reward / risk) >= 2.0:
                    note = f"{level_name}={level_val:.5f}"
                    return "SELL", sl, tp, last_close, f"Core: {note} Sweep. Bearish wick. H4:BEARISH. Vol:OK. UW={upper_wick:.5f}. R:R {reward/risk:.2f}"

    # Bullish: price swept PDL (or PWL) and closed back above with a clear lower wick
    if h4_bias == "BULLISH" and pdl < float('inf'):
        hits_pdl = sweep_low <= pdl
        hits_pwl  = pwl < float('inf') and sweep_low <= pwl
        level_hit  = hits_pdl or hits_pwl
        level_name = "PDL" if hits_pdl else "PWL"
        level_val  = pdl if hits_pdl else pwl

        if level_hit:
            wick_valid = (
                prev_close > sweep_low
                and prev_close > prev_open        # bullish closed candle
                and lower_wick > body_size
                and lower_wick > (0.4 * last_atr)
                and volume_confirmed
            )
            if wick_valid:
                # UPGRADE 3: Institutional SL just below wick low
                sl = prev_low - (0.3 * last_atr)
                tp = last_close + 2.5 * (last_close - sl)
                sl, tp = assess_risk("BUY", sl, tp, last_close, last_atr, "neutral")
                risk = last_close - sl
                reward = tp - last_close
                if risk > 0 and reward > 0 and (reward / risk) >= 2.0:
                    note = f"{level_name}={level_val:.5f}"
                    return "BUY", sl, tp, last_close, f"Core: {note} Sweep. Bullish wick. H4:BULLISH. Vol:OK. LW={lower_wick:.5f}. R:R {reward/risk:.2f}"
            
    return "NEUTRAL", 0.0, 0.0, 0.0, f"No core setup. H4:{h4_bias}, PDH:{pdh:.5f}, PDL:{pdl:.5f}"

def analyze_breakout_df(df: pd.DataFrame, symbol: str):
    """
    Order Block Detection Strategy — replaces naive BB breakout.
    
    A Bullish Order Block is the LAST bearish (red) candle before a significant
    bullish impulse move. Institutions leave buy orders in this zone.
    When price returns to the Order Block, institutions absorb it and price reverses.
    
    A Bearish Order Block is the LAST bullish (green) candle before a significant
    bearish impulse move. When price returns, institutions sell again.
    
    Improvements over old Breakout:
    1. H4 bias required — only trade OBs in the direction of the higher trend.
    2. Institutional SL — placed beyond the Order Block body, not at BB mid.
    3. Volume confirmation on the impulse move that created the OB.
    4. R:R minimum 2.5 for OB entries (slightly stricter — OBs are high probability).
    """
    if len(df) < 50:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data"

    df = df.copy()
    df = calculate_atr(df)
    df = calculate_rsi(df)

    last     = df.iloc[-1]
    last_close = last['close']
    last_atr   = last['atr']
    last_rsi   = last['rsi']

    # H4 bias is mandatory for Order Block entries
    h4_bias = get_h4_bias(symbol)
    if h4_bias == "NEUTRAL":
        return "NEUTRAL", 0.0, 0.0, 0.0, "H4 NEUTRAL — OB strategy requires clear trend"

    # Scan the last 30 closed candles to find the most recent valid Order Block
    # We skip the last 5 candles as they form the "return to OB" phase
    scan_zone = df.iloc[-35:-5]
    if len(scan_zone) < 15:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Not enough history for OB scan"

    avg_vol = df['tick_volume'].iloc[-30:-1].mean()

    # --- Bullish Order Block (H4 BULLISH only) ---
    if h4_bias == "BULLISH":
        # Find the last bearish candle before a bullish impulse (3+ green candles up)
        best_ob = None
        for i in range(len(scan_zone) - 4, 0, -1):
            candle = scan_zone.iloc[i]
            if candle['close'] >= candle['open']:
                continue  # not bearish, skip
            # Check if the next 3 candles are a bullish impulse
            next_3 = scan_zone.iloc[i+1:i+4]
            if len(next_3) < 3:
                continue
            all_bullish = all(next_3['close'] > next_3['open'])
            impulse_size = next_3['close'].iloc[-1] - candle['low']
            if all_bullish and impulse_size > (2.0 * last_atr):
                # Valid bullish OB found — record it
                # Volume on the impulse candles should be above average
                impulse_vol = next_3['tick_volume'].mean()
                if impulse_vol >= 1.1 * avg_vol:
                    best_ob = candle
                    break  # Use the most recent valid OB

        if best_ob is not None:
            ob_high = best_ob['high']
            ob_low  = best_ob['low']
            ob_mid  = (ob_high + ob_low) / 2
            # Price must currently be returning INTO the OB zone
            if ob_low <= last_close <= ob_high and last_rsi <= 50:
                sl = ob_low - (0.3 * last_atr)
                tp = last_close + 3.0 * (last_close - sl)
                sl, tp = assess_risk("BUY", sl, tp, last_close, last_atr, "neutral")
                risk = last_close - sl
                reward = tp - last_close
                if risk > 0 and reward > 0 and (reward / risk) >= 2.5:
                    return "BUY", sl, tp, last_close, f"Bullish OB entry [{ob_low:.5f}-{ob_high:.5f}]. H4:BULLISH. RSI:{last_rsi:.1f}. R:R {reward/risk:.2f}"

    # --- Bearish Order Block (H4 BEARISH only) ---
    if h4_bias == "BEARISH":
        best_ob = None
        for i in range(len(scan_zone) - 4, 0, -1):
            candle = scan_zone.iloc[i]
            if candle['close'] <= candle['open']:
                continue  # not bullish, skip
            next_3 = scan_zone.iloc[i+1:i+4]
            if len(next_3) < 3:
                continue
            all_bearish = all(next_3['close'] < next_3['open'])
            impulse_size = candle['high'] - next_3['close'].iloc[-1]
            if all_bearish and impulse_size > (2.0 * last_atr):
                impulse_vol = next_3['tick_volume'].mean()
                if impulse_vol >= 1.1 * avg_vol:
                    best_ob = candle
                    break

        if best_ob is not None:
            ob_high = best_ob['high']
            ob_low  = best_ob['low']
            if ob_low <= last_close <= ob_high and last_rsi >= 50:
                sl = ob_high + (0.3 * last_atr)
                tp = last_close - 3.0 * (sl - last_close)
                sl, tp = assess_risk("SELL", sl, tp, last_close, last_atr, "neutral")
                risk = sl - last_close
                reward = last_close - tp
                if risk > 0 and reward > 0 and (reward / risk) >= 2.5:
                    return "SELL", sl, tp, last_close, f"Bearish OB entry [{ob_low:.5f}-{ob_high:.5f}]. H4:BEARISH. RSI:{last_rsi:.1f}. R:R {reward/risk:.2f}"

    return "NEUTRAL", 0.0, 0.0, 0.0, f"No OB setup. H4:{h4_bias}. Close:{last_close:.5f}"


def analyze_gold_system_df(df: pd.DataFrame, symbol: str):
    """
    Gold-Specific Trading Strategy (XAUUSDm).
    Gold moves differently from Forex and indices. Key characteristics:
    - Gold is highly sensitive to USD strength (inverse relationship)
    - Gold respects round numbers ($100 increments) as psychological levels
    - Gold makes sharp liquidity sweeps during London open (07:00-09:00 UTC)
      and NY open (13:00-14:30 UTC) before reversing
    - Gold trends strongly — mean-reversion works best only at extremes

    Entry logic:
    1. H4 bias for trend direction (same as other strategies)
    2. Previous Day High/Low sweep + wick rejection on closed candle
    3. Round number confluence — price must be near a $100 or $50 round level
    4. RSI divergence check — price makes new extreme but RSI is improving
    5. Institutional SL just beyond the wick extreme
    6. Minimum R:R of 2.5 (Gold has wide spreads, needs higher reward)
    """
    if len(df) < 50:
        return "NEUTRAL", 0.0, 0.0, 0.0, "Insufficient data for Gold System"

    df = df.copy()
    df = calculate_atr(df)
    df = calculate_rsi(df)
    df['ema21'] = calculate_ema(df, 21)
    df['ema50'] = calculate_ema(df, 50)

    last = df.iloc[-1]
    prev = df.iloc[-2]  # Closed candle for geometry

    last_close = last['close']
    last_atr   = last['atr']
    last_rsi   = last['rsi']
    last_ema21 = last['ema21']
    last_ema50 = last['ema50']

    # H4 Bias
    h4_bias = get_h4_bias(symbol)
    if h4_bias == "NEUTRAL":
        return "NEUTRAL", 0.0, 0.0, 0.0, "Gold: H4 NEUTRAL — waiting for clear trend"

    # Previous Day High/Low
    pdh, pdl = 0.0, float('inf')
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 3)
    if rates_d1 is not None and len(rates_d1) >= 1:
        pdh = rates_d1[0]['high']
        pdl = rates_d1[0]['low']
    if pdh == 0.0 or pdl == float('inf'):
        return "NEUTRAL", 0.0, 0.0, 0.0, "Gold: Cannot read Daily levels"

    # Previous Week High/Low for confluence
    pwh, pwl = 0.0, float('inf')
    rates_w1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 1, 2)
    if rates_w1 is not None and len(rates_w1) >= 1:
        pwh = rates_w1[0]['high']
        pwl = rates_w1[0]['low']

    # Closed candle geometry
    prev_close = prev['close']
    prev_open  = prev['open']
    prev_high  = prev['high']
    prev_low   = prev['low']
    prev_rsi   = prev['rsi']
    prev_vol   = prev['tick_volume']

    body_size  = abs(prev_close - prev_open)
    lower_wick = min(prev_close, prev_open) - prev_low
    upper_wick = prev_high - max(prev_close, prev_open)

    # Volume filter
    avg_vol = df['tick_volume'].iloc[-21:-1].mean() if len(df) >= 21 else df['tick_volume'].mean()
    volume_ok = prev_vol >= 1.2 * avg_vol

    # Round number confluence — Gold respects $50 and $100 levels
    # Check if the PDH/PDL is near a $50 round number (e.g. 2300, 2350, 2400)
    def near_round_level(price, tolerance=8.0):
        """Returns True if price is within tolerance of a $50 increment."""
        nearest_50 = round(price / 50) * 50
        return abs(price - nearest_50) <= tolerance

    # Recent sweep high/low across last 20 candles
    recent = df.iloc[-20:]
    sweep_high = recent['high'].max()
    sweep_low  = recent['low'].min()

    # --- RSI Divergence check (simplified) ---
    # For BUY: price swept lower than PDL, but RSI is not making new lows (improving)
    rsi_diverge_buy  = prev_rsi < 40 and prev_rsi > df['rsi'].iloc[-10:-2].min()
    rsi_diverge_sell = prev_rsi > 60 and prev_rsi < df['rsi'].iloc[-10:-2].max()

    action = "NEUTRAL"
    sl = 0.0
    tp = 0.0
    round_note = ""

    # --- SELL Setup: H4 Bearish, PDH swept, bearish wick rejection ---
    if h4_bias == "BEARISH" and pdh > 0:
        pdh_swept = sweep_high >= pdh - (0.1 * last_atr)  # slight tolerance for Gold
        pwh_swept = pwh > 0 and sweep_high >= pwh - (0.1 * last_atr)

        if pdh_swept or pwh_swept:
            level_val  = pdh if pdh_swept else pwh
            level_name = "PDH" if pdh_swept else "PWH"
            round_ok   = near_round_level(level_val)
            round_note = f" Round ${round(level_val/50)*50:.0f}" if round_ok else ""

            wick_valid = (
                prev_close < prev_open           # bearish closed candle
                and prev_close < sweep_high       # closed back below swept high
                and upper_wick > body_size
                and upper_wick > (0.5 * last_atr) # Gold needs bigger wick (wider spread)
                and volume_ok
            )
            if wick_valid:
                sl = prev_high + (0.5 * last_atr)  # slightly wider for Gold spread
                tp = last_close - 2.5 * (sl - last_close)
                sl, tp = assess_risk("SELL", sl, tp, last_close, last_atr, "neutral")
                risk = sl - last_close
                reward = last_close - tp
                if risk > 0 and reward > 0 and (reward / risk) >= 2.5:
                    div_note = " [RSI Div]" if rsi_diverge_sell else ""
                    return "SELL", sl, tp, last_close, f"Gold SELL: {level_name}{round_note}{div_note}. H4:BEARISH. Vol:OK. UW={upper_wick:.2f}. R:R {reward/risk:.2f}"

    # --- BUY Setup: H4 Bullish, PDL swept, bullish wick rejection ---
    if h4_bias == "BULLISH" and pdl < float('inf'):
        pdl_swept = sweep_low <= pdl + (0.1 * last_atr)
        pwl_swept = pwl < float('inf') and sweep_low <= pwl + (0.1 * last_atr)

        if pdl_swept or pwl_swept:
            level_val  = pdl if pdl_swept else pwl
            level_name = "PDL" if pdl_swept else "PWL"
            round_ok   = near_round_level(level_val)
            round_note = f" Round ${round(level_val/50)*50:.0f}" if round_ok else ""

            wick_valid = (
                prev_close > prev_open           # bullish closed candle
                and prev_close > sweep_low        # closed back above swept low
                and lower_wick > body_size
                and lower_wick > (0.5 * last_atr)
                and volume_ok
            )
            if wick_valid:
                sl = prev_low - (0.5 * last_atr)
                tp = last_close + 2.5 * (last_close - sl)
                sl, tp = assess_risk("BUY", sl, tp, last_close, last_atr, "neutral")
                risk = last_close - sl
                reward = tp - last_close
                if risk > 0 and reward > 0 and (reward / risk) >= 2.5:
                    div_note = " [RSI Div]" if rsi_diverge_buy else ""
                    return "BUY", sl, tp, last_close, f"Gold BUY: {level_name}{round_note}{div_note}. H4:BULLISH. Vol:OK. LW={lower_wick:.2f}. R:R {reward/risk:.2f}"

    return "NEUTRAL", 0.0, 0.0, 0.0, f"Gold: No setup. H4:{h4_bias}, PDH:{pdh:.2f}, PDL:{pdl:.2f}, Close:{last_close:.2f}"


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
                elif strategy == "gold_system":
                    res = analyze_gold_system_df(df, symbol)
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
        mt5.login(MT5_CONFIG["login"], password=MT5_CONFIG["password"], server=MT5_CONFIG["server"])
        logger.info("AlphaEdge Strategy initialized.")
    except Exception as e:
        logger.error(f"MT5 connection failed: {e}")
        raise RuntimeError(f"MT5 connection failed: {e}")
        
    prop_engine = None
    if PROP_FIRM_MODE:
        prop_engine = PropFirmEngine(starting_balance=PROP_FIRM_STARTING_BALANCE, current_phase=1)
        
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
    
    def liquidate_all_positions(reason: str):
        """Close all open positions immediately. Used for Friday weekend block and drawdown kill."""
        positions = mt5.positions_get()
        if not positions:
            logger.info(f"[{reason}] No open positions to close.")
            return
        closed = 0
        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                continue
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": close_price,
                "deviation": 30,
                "magic": pos.magic,
                "comment": f"Auto-Close: {reason}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"[{reason}] Closed {pos.symbol} ticket {pos.ticket}")
                closed += 1
            else:
                logger.error(f"[{reason}] Failed to close {pos.symbol}: {getattr(result, 'comment', mt5.last_error())}")
        if closed > 0:
            send_telegram_alert(f"🚨 <b>[{reason}]</b>\nClosed {closed} open position(s) to protect Prop Firm account.")

    if PROP_FIRM_MODE and (prop_firm_locked or friday_block):
        if prop_firm_locked:
            logger.info("-> 🚨 Prop Firm Daily Drawdown Kill Switch Active. Scanning disabled.")
            liquidate_all_positions("Drawdown Liquidation")
        elif friday_block:
            logger.info("-> 🚫 Friday Weekend Block Active (Post 21:00 UTC). Liquidating all positions.")
            liquidate_all_positions("Weekend Liquidation")
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
