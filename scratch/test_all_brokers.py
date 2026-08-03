# test_all_brokers.py
"""Test script to place a small BUY order on both Deriv and Exness brokers.
It uses the credentials defined in trade_config.py and places a test trade
for a few symbols with the minimum lot size. The order comment is set to
"ALPHAEDGE_TRADE" so that the bot can recognise and manage it.
"""

import sys
import os
from pathlib import Path
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Ensure the trade_config module can be imported
BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / ".agents" / "trading_bot_skills"
sys.path.append(str(CONFIG_PATH))
from trade_config import DERIV_CONFIG, EXNESS_CONFIG, MT5_PATH


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate Average True Range (ATR) for a DataFrame of rates.
    The function adds an ``atr`` column to the DataFrame.
    """
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(np.abs(df["high"] - df["prev_close"]), np.abs(df["low"] - df["prev_close"]))
    )
    df["atr"] = df["tr"].rolling(window=period).mean()
    df["atr"] = df["atr"].fillna(df["high"] - df["low"])  # fallback
    return df


def send_test_buy(symbol: str) -> None:
    """Place a single BUY order for *symbol* using the currently active MT5 session.
    The order uses the minimum allowed lot size and a simple SL/TP based on ATR.
    """
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"[WARN] Symbol {symbol} not found.")
        return
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"[WARN] Could not select symbol {symbol}.")
            return
    # Fetch recent rates for ATR calculation
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 30)
    if rates is None or len(rates) < 15:
        print(f"[WARN] Insufficient rate data for {symbol}.")
        return
    df = pd.DataFrame(rates)
    df = calculate_atr(df)
    atr = df["atr"].iloc[-1]
    if atr <= 0:
        atr = info.point * 100
    price = mt5.symbol_info_tick(symbol).ask
    sl = price - 3.0 * atr
    tp = price + 5.0 * atr
    volume = info.volume_min
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "comment": "ALPHAEDGE_TRADE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[OK] Test BUY placed on {symbol} – Ticket {result.order}, SL {sl:.5f}, TP {tp:.5f}")
    else:
        err = result.comment if result else "N/A"
        code = result.retcode if result else "N/A"
        print(f"[ERROR] Failed to place test BUY on {symbol}: {err} (Retcode: {code})")


def run_test(config: dict, broker_name: str) -> None:
    """Initialise MT5 with *config* and place test buys on a set of symbols.
    For Deriv we optionally pass a custom MT5 executable path (MT5_PATH).
    """
    print(f"\n=== Connecting to {broker_name} ===")
    init_kwargs = {
        "login": config["login"],
        "password": config["password"],
        "server": config["server"],
    }
    # Use custom terminal path for Deriv if provided
    if broker_name.lower().startswith("deriv") and MT5_PATH:
        init_kwargs["path"] = MT5_PATH
    mt5.shutdown()
    if not mt5.initialize(**init_kwargs):
        print(f"[ERROR] Could not initialise MT5 for {broker_name}")
        return
    for sym in ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]:
        send_test_buy(sym)
    mt5.shutdown()
    print(f"=== {broker_name} test completed ===\n")

    """Initialise MT5 with *config* and place test buys on a set of symbols."""
    print(f"\n=== Connecting to {broker_name} ===")
    if not mt5.initialize(login=config["login"], password=config["password"], server=config["server"]):
        print(f"[ERROR] Could not initialise MT5 for {broker_name}")
        return
    for sym in ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]:
        send_test_buy(sym)
    mt5.shutdown()
    print(f"=== {broker_name} test completed ===\n")


def main():
    # Test Deriv
    run_test(DERIV_CONFIG, "Deriv (Demo)")
    # Test Exness
    run_test(EXNESS_CONFIG, "Exness (MT5 Trial)")

if __name__ == "__main__":
    main()
