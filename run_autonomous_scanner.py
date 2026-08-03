# run_autonomous_scanner.py
# Runs alphaedge and sherifnew scans autonomously every 5 minutes.

import sys
import os
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("autonomous_trading.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("AutonomousScanner")

# Add scratch path to sys.path to import strategy modules
scratch_dir = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch"
if scratch_dir not in sys.path:
    sys.path.insert(0, scratch_dir)

# Import strategies
try:
    import alphaedge
    logger.info("Successfully imported AlphaEdge strategy.")
except Exception as e:
    logger.error(f"Error importing strategy modules: {e}")
    sys.exit(1)

INTERVAL_SECONDS = 120  # 2 minutes

def main():
    logger.info("=== Starting Autonomous Strategy Trader (2-Minute Cycle) ===")
    
    while True:
        cycle_start = datetime.now()
        logger.info(f"--- Starting scan cycle at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        # 1. Run AlphaEdge Strategy Scan
        try:
            logger.info("Running AlphaEdge scan...")
            alphaedge.run_alphaedge()
        except Exception as e:
            logger.error(f"Error executing AlphaEdge scan: {e}")
            
        cycle_end = datetime.now()
        elapsed = (cycle_end - cycle_start).total_seconds()
        sleep_time = max(0, INTERVAL_SECONDS - elapsed)
        
        logger.info(f"Cycle completed in {elapsed:.1f}s. Next scan in {sleep_time/60:.1f} minutes.\n")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
