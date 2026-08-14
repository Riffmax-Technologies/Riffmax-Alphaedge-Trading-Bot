# run_autonomous_scanner.py
# Runs AlphaEdge scans autonomously every 5 minutes.

import sys
import time
import logging
from datetime import datetime

import alphaedge
from desktop_trade_report import refresh_report
from performance_report import generate_performance_report

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
    logger.info("=== Starting Autonomous Strategy Trader (1-Minute Hyper-Scan Cycle) ===")
    
    last_daily_report_date = None
    last_weekly_report_date = None
    
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
                    
            # 2. Daily and Weekly Reporting Schedule (Runs at 23:55 UTC)
            now = datetime.now()
            today_date = now.date()
            if now.hour == 23 and now.minute >= 50:
                # Daily Report
                if last_daily_report_date != today_date:
                    try:
                        logger.info("Generating Daily Performance Report...")
                        start_time = datetime(now.year, now.month, now.day)
                        end_time = start_time + timedelta(days=1)
                        daily_msg = generate_performance_report(start_time, end_time, "Daily")
                        send_telegram_alert(daily_msg)
                        last_daily_report_date = today_date
                    except Exception as e:
                        logger.error(f"Failed to send daily report: {e}")
                        
                # Weekly Report (Friday)
                if now.weekday() == 4 and last_weekly_report_date != today_date:
                    try:
                        logger.info("Generating Weekly Performance Report...")
                        start_time = datetime(now.year, now.month, now.day) - timedelta(days=4)  # Monday
                        end_time = datetime(now.year, now.month, now.day) + timedelta(days=1)    # Friday end
                        weekly_msg = generate_performance_report(start_time, end_time, "Weekly")
                        send_telegram_alert(weekly_msg)
                        last_weekly_report_date = today_date
                    except Exception as e:
                        logger.error(f"Failed to send weekly report: {e}")
                
            cycle_end = datetime.now()
            elapsed = (cycle_end - cycle_start).total_seconds()
            sleep_time = max(0, 60 - elapsed)
            logger.info(f"Cycle completed in {elapsed:.1f}s. Sleeping for {sleep_time:.1f}s...")
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
