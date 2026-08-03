import logging
# from trading_bot_skills.trade_config import SCAN_INTERVAL_MINUTES, MANUAL_TRIGGER_KEY  # moved later
import sys
import os
from pathlib import Path

# Ensure the '.agents' package is on the Python path so we can import trading_bot_skills
agents_path = Path(__file__).parent / '.agents'
if agents_path.is_dir():
    sys.path.insert(0, str(agents_path))
else:
    logging.warning(f"Agents directory not found at {agents_path}")

# Import configuration after agents path is added to sys.path
from trading_bot_skills.trade_config import SCAN_INTERVAL_MINUTES, MANUAL_TRIGGER_KEY

# Basic logging (console + file)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / 'autonomous_alphaedge.log'),
    ],
)

# Absolute imports – now that .agents is on the path
try:
    from trading_bot_skills import trade_logger, indicators, risk, trade_executor
except Exception as e:
    logging.warning(f"Failed to import trading_bot_skills: {e}")
    trade_logger = None

def run_scan():
    """Entry point for the manual AlphaEdge scan.
    Uses configuration from trade_config for schedule and trigger key.
    """
    logging.info('=== AlphaEdge manual scan started ===')
    logging.info(f'Configured scan interval: {SCAN_INTERVAL_MINUTES} minutes')
    logging.info(f'Manual trigger key: {MANUAL_TRIGGER_KEY}')
    if trade_logger:
        try:
            trade_logger.init_logger()
            logging.info('Trade logger initialized.')
            # Example placeholder trade execution – replace with real signal logic
            trade_executor.execute_trade(
                symbol="EURUSD",
                action="BUY",
                entry_price=1.1000,
                atr=0.0010,
                profit=0.0,
                comment="Demo trade"
            )
        except Exception as e:
            logging.error(f"Error during trade logger init or execution: {e}")
    else:
        logging.info('Trade logger not available – continuing without it.')
    # Placeholder for additional scan logic
    logging.info('AlphaEdge placeholder scan completed.')

if __name__ == "__main__":
    run_scan()
