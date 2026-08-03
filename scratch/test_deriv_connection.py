# test_deriv_connection.py
"""Attempt to initialise MetaTrader5 with Deriv demo credentials and print the result.
If the connection fails, the error code and message are displayed.
"""

import sys
from pathlib import Path
import MetaTrader5 as mt5

# Add trade_config to path
BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / ".agents" / "trading_bot_skills"
sys.path.append(str(CONFIG_PATH))

try:
    from trade_config import DERIV_CONFIG
except Exception as e:
    print(f"Failed to import DERIV_CONFIG: {e}")
    sys.exit(1)

print("Attempting to initialise MT5 for Deriv Demo...")
if mt5.initialize(login=DERIV_CONFIG["login"], password=DERIV_CONFIG["password"], server=DERIV_CONFIG["server"]):
    print("✅ Successfully initialised Deriv MT5 connection.")
    mt5.shutdown()
else:
    last_error = mt5.last_error()
    print(f"❌ MT5 initialise failed. Error: {last_error}")
    sys.exit(1)
