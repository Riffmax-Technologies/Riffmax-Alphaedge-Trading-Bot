# Simple risk assessment utilities for AlphaEdge

# Import configuration constants
from .trade_config import ACCOUNT_BALANCE, MAX_LOSS_PER_TRADE_PCT, LOT_SIZE_FACTOR, MAX_DAILY_DRAWDOWN_PCT, MAX_OVERALL_DRAWDOWN_PCT, DAILY_PNL_PATH
import logging
from datetime import datetime
def assess_risk(action: str, sl: float, tp: float, entry_price: float, atr: float, risk_level: str = "neutral") -> tuple[float, float]:
    """
    Adjust stop‑loss and take‑profit based on risk appetite.

    Parameters
    ----------
    action: "BUY" or "SELL"
    sl, tp: original stop‑loss and take‑profit values
    entry_price: price at which the trade would be entered
    atr: Average True Range for the symbol (already calculated)
    risk_level: "aggressive", "conservative" or "neutral"

    Returns
    -------
    (new_sl, new_tp): adjusted values
    """
    if risk_level == "aggressive":
        # tighter SL (closer to entry) and larger TP for higher risk/reward
        if action == "BUY":
            new_sl = entry_price - 0.5 * atr
            new_tp = entry_price + 1.5 * atr
        else:  # SELL
            new_sl = entry_price + 0.5 * atr
            new_tp = entry_price - 1.5 * atr
    elif risk_level == "conservative":
        # looser SL (more protection) and tighter TP
        if action == "BUY":
            new_sl = entry_price - 1.5 * atr
            new_tp = entry_price + 0.5 * atr
        else:  # SELL
            new_sl = entry_price + 1.5 * atr
            new_tp = entry_price - 0.5 * atr
    else:
        # neutral – keep original values
        new_sl, new_tp = sl, tp
    return new_sl, new_tp


def max_lot_for_risk(entry_price: float, atr: float) -> float:
    """Calculate a safe lot size based on maximum allowed loss per trade.

    The maximum loss per trade is defined as a percentage of the account balance.
    This function returns a lot multiplier that, when applied to the default lot
    (usually 1.0), ensures the potential loss does not exceed that threshold.
    """
    max_loss_amount = ACCOUNT_BALANCE * (MAX_LOSS_PER_TRADE_PCT / 100.0)
    # Approximate per‑lot loss assuming a stop loss placed at 1 ATR distance.
    # For many brokers 1 lot = 100,000 units; we approximate $ loss ≈ ATR * lot.
    # This is a rough estimate; adjust as needed for the specific instrument.
    if atr == 0:
        return LOT_SIZE_FACTOR
    lot = max_loss_amount / atr
    # Apply global scaling factor to keep lots small overall.
    return lot * LOT_SIZE_FACTOR

# ---------------------------------------------------------------------------
# Drawdown tracking utilities
# ---------------------------------------------------------------------------
import json
from pathlib import Path
from .trade_config import ACCOUNT_BALANCE, DAILY_PNL_PATH, MAX_DAILY_DRAWDOWN_PCT, MAX_OVERALL_DRAWDOWN_PCT

def _load_daily_pnl() -> dict:
    """Load or initialize the daily PnL JSON file.

    Returns a dict with keys: date, balance, daily_profit, overall_profit.
    """
    if not DAILY_PNL_PATH.exists():
        # Initialize with zeros
        data = {
            "date": datetime.utcnow().strftime('%Y-%m-%d'),
            "balance": ACCOUNT_BALANCE,
            "daily_profit": 0.0,
            "overall_profit": 0.0,
        }
        DAILY_PNL_PATH.write_text(json.dumps(data, indent=2))
        return data
    try:
        data = json.loads(DAILY_PNL_PATH.read_text())
    except Exception:
        data = {
            "date": datetime.utcnow().strftime('%Y-%m-%d'),
            "balance": ACCOUNT_BALANCE,
            "daily_profit": 0.0,
            "overall_profit": 0.0,
        }
    # Reset daily profit if date changed
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    if data.get("date") != today_str:
        data["date"] = today_str
        data["daily_profit"] = 0.0
    return data

def _save_daily_pnl(data: dict) -> None:
    DAILY_PNL_PATH.write_text(json.dumps(data, indent=2))

def get_daily_drawdown() -> float:
    """Return the current daily loss amount (positive number) if any.
    """
    data = _load_daily_pnl()
    loss = -data.get("daily_profit", 0.0)
    return max(loss, 0.0)

def get_overall_drawdown() -> float:
    data = _load_daily_pnl()
    loss = -data.get("overall_profit", 0.0)
    return max(loss, 0.0)

def check_drawdown_limits() -> bool:
    """Return True if still within allowed drawdown limits, False otherwise.
    """
    daily_loss = get_daily_drawdown()
    overall_loss = get_overall_drawdown()
    daily_limit = ACCOUNT_BALANCE * (MAX_DAILY_DRAWDOWN_PCT / 100.0)
    overall_limit = ACCOUNT_BALANCE * (MAX_OVERALL_DRAWDOWN_PCT / 100.0)
    if daily_loss > daily_limit:
        logging.warning(f"Daily drawdown limit exceeded: ${daily_loss:.2f} > ${daily_limit:.2f}")
        return False
    if overall_loss > overall_limit:
        logging.warning(f"Overall drawdown limit exceeded: ${overall_loss:.2f} > ${overall_limit:.2f}")
        return False
    return True

