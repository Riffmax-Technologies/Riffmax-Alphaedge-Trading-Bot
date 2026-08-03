# trade_executor.py – handles order placement with risk checks

import logging
import pathlib
from datetime import datetime
import MetaTrader5 as mt5
import atexit

# Local imports
from . import risk
from . import trade_logger
from .trade_config import DAILY_PNL_PATH, ACCOUNT_BALANCE, MAX_LOSS_PER_TRADE_PCT, LOT_SIZE_FACTOR, MAX_LOT_SIZE, SL_MULTIPLIER, TP_MULTIPLIER

# Initialize MT5 connection when module loads
if not mt5.initialize():
    logging.error(f"Failed to initialize MT5: {mt5.last_error()}")
else:
    logging.info("MT5 initialized successfully.")

# Ensure MT5 shutdown on exit
atexit.register(mt5.shutdown)


def _update_daily_pnl(profit: float) -> None:
    """Update the daily PnL JSON with the realized profit/loss of a trade.

    The JSON file is created/maintained by ``risk._load_daily_pnl``.
    """
    # Load existing data (reuse the internal loader from risk)
    data = risk._load_daily_pnl()
    data["daily_profit"] = data.get("daily_profit", 0.0) + profit
    data["overall_profit"] = data.get("overall_profit", 0.0) + profit
    risk._save_daily_pnl(data)


def mt5_send_order(symbol: str, action: str, lots: float, sl: float, tp: float) -> bool:
    """Send a real order to MetaTrader 5.

    Returns ``True`` if the order was placed successfully, otherwise ``False``.
    """
    # Prepare request dictionary
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logging.error(f"Symbol info not available for {symbol}")
        return False
    price = tick.ask if action == "BUY" else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": round(lots, 2),
        "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": "AlphaEdge_TRADE",
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"MT5 order failed for {symbol} retcode={result.retcode}")
        return False
    logging.info(f"MT5 order placed: ticket={result.order}, price={price}, lots={lots:.4f}")
    return True


def execute_trade(
    symbol: str,
    action: str,
    entry_price: float,
    atr: float,
    profit: float = 0.0,
    comment: str = "AlphaEdge_TRADE",
) -> bool:
    """Execute a trade with full risk validation.

    Steps:
    1. Verify daily/overall drawdown limits are still within allowed bounds.
    2. Compute a safe lot size using ``risk.max_lot_for_risk``.
    3. Send the order via the MT5 stub (or real API).
    4. Log the trade and update daily PnL.
    """
    if not risk.check_drawdown_limits():
        logging.warning("Trade aborted – drawdown limits exceeded.")
        return False

    # Determine a safe lot size based on the configured risk parameters.
    max_loss_amount = ACCOUNT_BALANCE * (MAX_LOSS_PER_TRADE_PCT / 100.0)
    if atr == 0:
        lots = LOT_SIZE_FACTOR
    else:
        lot = max_loss_amount / atr
        lots = min(lot * LOT_SIZE_FACTOR, MAX_LOT_SIZE)

    logging.info(f"Calculated safe lot size (capped): {lots:.4f}")

    # Calculate SL and TP using ATR multipliers
    if action == "BUY":
        sl_price = entry_price - SL_MULTIPLIER * atr
        tp_price = entry_price + TP_MULTIPLIER * atr
    else:  # SELL
        sl_price = entry_price + SL_MULTIPLIER * atr
        tp_price = entry_price - TP_MULTIPLIER * atr
    # Retrieve symbol info for precision and minimum stop level
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        logging.error(f"Symbol info not available for {symbol}")
        return False
    # Ensure prices respect minimum stop distance
    min_stop = sym_info.trade_stops_level * sym_info.point
    # Use current market price for stop calculations
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logging.error(f"Tick info not available for {symbol}")
        return False
    price = tick.bid if action == "BUY" else tick.ask
    if action == "BUY":
        sl_price = max(sl_price, price - min_stop)
        tp_price = max(tp_price, price + min_stop)
        if sl_price >= price:
            # Adjust SL to be just below market price
            sl_price = price - max(min_stop, sym_info.point)
    else:
        sl_price = min(sl_price, price + min_stop)
        tp_price = min(tp_price, price - min_stop)
        if sl_price <= price:
            sl_price = price + max(min_stop, sym_info.point)
    # Validate SL side relative to market price
    if action == "BUY" and sl_price >= price:
        logging.error("Invalid SL: SL not below market price for BUY")
        return False
    if action == "SELL" and sl_price <= price:
        logging.error("Invalid SL: SL not above market price for SELL")
        return False
    # Normalize to symbol precision
    digits = sym_info.digits
    sl_price = round(sl_price, digits)
    tp_price = round(tp_price, digits)

    # Attempt to place the order.
    success = mt5_send_order(symbol, action, lots, sl_price, tp_price)
    if not success:
        logging.error("MT5 order placement failed.")
        return False

    # Log the trade – profit may be zero for an open position.
    trade_logger.log_trade(symbol, action, entry_price, sl_price, tp_price, profit, comment)

    # Update the PnL tracking file.
    if profit != 0:
        _update_daily_pnl(profit)

    logging.info("Trade execution completed successfully.")
    return True
