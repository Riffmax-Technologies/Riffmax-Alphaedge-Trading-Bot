import os
import pandas as pd
from datetime import datetime

# Path to the Excel log file on the Desktop (public desktop as per user selection)
LOG_FILE_PATH = r"C:\Users\Public\Desktop\trade_log.xlsx"

# Column headers for the trade log
COLUMNS = [
    "timestamp",
    "symbol",
    "action",
    "entry_price",
    "sl",
    "tp",
    "profit",
    "comment",
]

def _ensure_log_file():
    """Create the Excel file with headers if it does not exist."""
    if not os.path.exists(LOG_FILE_PATH):
        df = pd.DataFrame(columns=COLUMNS)
        # Use openpyxl engine to create an .xlsx file
        df.to_excel(LOG_FILE_PATH, index=False, engine="openpyxl")

def log_trade(symbol: str, action: str, entry_price: float, sl: float, tp: float, profit: float, comment: str):
    """Append a single trade record to the Excel log.

    Parameters
    ----------
    symbol: Trading symbol.
    action: "BUY" or "SELL".
    entry_price: Price at which the trade was entered.
    sl: Stop‑loss price.
    tp: Take‑profit price.
    profit: Realised profit (0 if the trade is just opened).
    comment: Trade comment (e.g., "ALPHAEDGE_TRADE").
    """
    _ensure_log_file()
    # Load existing data, append new row, and write back
    try:
        df = pd.read_excel(LOG_FILE_PATH, engine="openpyxl")
    except Exception:
        df = pd.DataFrame(columns=COLUMNS)
    new_row = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "action": action,
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "profit": profit,
        "comment": comment,
    }
    df = df.append(new_row, ignore_index=True)
    df.to_excel(LOG_FILE_PATH, index=False, engine="openpyxl")
