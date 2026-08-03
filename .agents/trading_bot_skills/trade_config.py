# trade_config.py – configuration for the AlphaEdge bot

from pathlib import Path

# Account parameters (prop‑firm account)
ACCOUNT_BALANCE = 10_000  # USD
MAX_DAILY_DRAWDOWN_PCT = 2.0  # percent of account (prop firm limit)
# Maximum lot size (in standard lots) to prevent oversized orders
MAX_OVERALL_DRAWDOWN_PCT = 5.0  # percent of account (overall limit)
MAX_LOT_SIZE = 0.03
PROFIT_TARGET_PCT = 5.0  # percent of account

# Path for daily PnL tracking JSON file
DAILY_PNL_PATH = Path(__file__).parent / "daily_pnl.json"

# Lot sizing – factor to scale down the default lot size
# A factor of 0.10 means each trade will use 10 % of the original lot size
LOT_SIZE_FACTOR = 0.10
SL_MULTIPLIER = 3.0
TP_MULTIPLIER = 5.0

# Risk control
# Maximum loss per trade as a percent of the account (e.g., 0.2% -> $20)
MAX_LOSS_PER_TRADE_PCT = 0.2

# Manual trigger key for immediate scans (change as needed)
MANUAL_TRIGGER_KEY = "A"

# Scan schedule (minutes between automatic scans)
SCAN_INTERVAL_MINUTES = 10

# Telegram Alert Settings
TELEGRAM_ENABLED = True  # Set to True once you enter your token and chat ID
TELEGRAM_TOKEN = "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0"
TELEGRAM_CHAT_ID = "915238743"