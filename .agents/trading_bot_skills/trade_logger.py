import os
import pandas as pd
from datetime import datetime
import logging
# Path to the Excel log file on the Desktop (public desktop as per user selection)
LOG_FILE_PATH = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/trade_log.xlsx"

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
    # Append and save
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(LOG_FILE_PATH, index=False, engine="openpyxl")

def init_logger():
    """Initialize the trade logger and ensure the log file exists.

    This simple helper is called by the AlphaEdge scan before any trading activity.
    It creates the Excel file with the proper headers if it does not already exist
    and logs an informational message.
    """
    _ensure_log_file()
    logging.info('Trade logger initialized via init_logger()')
