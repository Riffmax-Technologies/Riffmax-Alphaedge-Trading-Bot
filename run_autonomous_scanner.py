# run_autonomous_scanner.py
# Runs AlphaEdge scans autonomously every 5 minutes.

import sys
import time
import logging
from datetime import datetime

import alphaedge
from desktop_trade_report import refresh_report

logging.basicConfig(
    level=logging.WARNING,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AutonomousScanner")

send_telegram_alert = alphaedge.send_telegram_alert
logger.info("Successfully imported AlphaEdge strategy.")

INTERVAL_SECONDS = 300  # 5 minutes

def main():
    logger.info("=== Starting Autonomous Strategy Trader (5-Minute Cycle) ===")
    
    try:
        while True:
            cycle_start = datetime.now()
            logger.info(f"--- Starting scan cycle at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            # Check for pause state
            from pathlib import Path
            state_file = Path("bot_state.txt")
            if state_file.exists() and state_file.read_text().strip().upper() == "STOPPED":
                logger.info("Scanner is currently PAUSED via Telegram. Skipping scan.")
            else:
                # 1. Run AlphaEdge Strategy Scan
                try:
                    logger.info("Running AlphaEdge scan...")
                    alphaedge.run_alphaedge(execute_orders=True)
                    try:
                        send_telegram_alert("✅ AlphaEdge autonomous scan completed.")
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error executing AlphaEdge scan: {e}")
                    send_telegram_alert(f"⚠️ <b>AlphaEdge Scan Error</b>\n{e}")
                
            cycle_end = datetime.now()
            elapsed = (cycle_end - cycle_start).total_seconds()
            sleep_time = max(0, INTERVAL_SECONDS - elapsed)
            
            logger.info(f"Cycle completed in {elapsed:.1f}s. Next scan in {sleep_time/60:.1f} minutes.\n")
            try:
                refresh_report(days_back=30)
                logger.info("Desktop trade report refreshed.")
            except Exception as report_error:
                logger.error(f"Failed to refresh desktop trade report: {report_error}")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        shutdown_msg = "🛑 <b>Bot Offline</b>\nThe AlphaEdge scanner has been manually shut down."
        logger.info("Bot manually stopped by user.")
        try:
            send_telegram_alert(shutdown_msg)
        except:
            pass
    except Exception as fatal_error:
        error_msg = f"🚨 <b>CRITICAL BOT FAILURE</b> 🚨\nThe autonomous scanner has stopped working!\nError: {fatal_error}"
        logger.critical(error_msg)
        try:
            send_telegram_alert(error_msg)
        except:
            pass
        raise

if __name__ == "__main__":
    main()
