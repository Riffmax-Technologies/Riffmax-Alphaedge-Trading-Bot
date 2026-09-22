# run_autonomous_scanner.py
# Runs AlphaEdge scans autonomously every 1 minute.
# Signal Confirmation: A BUY/SELL must fire on 3 consecutive 1-min scans
#                      before any order is placed (filters false positives).
# Max Trades Per Symbol: 3 open positions per asset at any time.

import sys
import time
import logging
import MetaTrader5 as mt5
from collections import defaultdict
from datetime import datetime, timedelta

import alphaedge
from desktop_trade_report import refresh_report
from performance_report import generate_performance_report

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AutonomousScanner")

send_telegram_alert = alphaedge.send_telegram_alert
logger.info("Successfully loaded AlphaEdge Day Trading engine.")

MAX_TRADES_PER_SYMBOL = 1  # Exactly 1 active position per asset


def count_open_positions(symbol: str) -> int:
    """Return how many open MT5 positions exist for a given symbol."""
    positions = mt5.positions_get(symbol=symbol)
    return len(positions) if positions else 0


def main():
    logger.info("=" * 65)
    logger.info("  ALPHAEDGE INSTITUTIONAL DAY TRADER -- ACTIVE (1-Min Cycles)")
    logger.info("  Rules: M15 S&D + Fib 50% + H4 Trend | Max 1 Trade Per Asset")
    logger.info("=" * 65)

    last_daily_report_date  = None
    last_weekly_report_date = None

    try:
        while True:
            cycle_start = datetime.now()
            print("\n" + "-" * 65)
            logger.info(f"Scanning 10 assets at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}...")

            # ── Pause gate ────────────────────────────────────────────────────
            from pathlib import Path
            state_file = Path("bot_state.txt")
            if state_file.exists() and state_file.read_text().strip().upper() == "STOPPED":
                logger.info("Scanner is PAUSED via Telegram. Skipping scan.")
            else:
                try:
                    from institutional_trader import run_scalping_cycle
                    run_scalping_cycle()
                except Exception as e:
                    logger.error(f"Error executing Autonomous M1 Scalper: {e}")
                    send_telegram_alert(f"⚠️ <b>Autonomous Scalper Error</b>\n{e}")

            # ── Daily & Weekly Reporting (23:50 UTC) ───────────────────────────
            now        = datetime.now()
            today_date = now.date()
            if now.hour == 23 and now.minute >= 50:
                if last_daily_report_date != today_date:
                    try:
                        start_time = datetime(now.year, now.month, now.day)
                        end_time   = start_time + timedelta(days=1)
                        daily_msg  = generate_performance_report(start_time, end_time, "Daily")
                        send_telegram_alert(daily_msg)
                        last_daily_report_date = today_date
                    except Exception as e:
                        logger.error(f"Failed to send daily report: {e}")

                if now.weekday() == 4 and last_weekly_report_date != today_date:
                    try:
                        start_time  = datetime(now.year, now.month, now.day) - timedelta(days=4)
                        end_time    = datetime(now.year, now.month, now.day) + timedelta(days=1)
                        weekly_msg  = generate_performance_report(start_time, end_time, "Weekly")
                        send_telegram_alert(weekly_msg)
                        last_weekly_report_date = today_date
                    except Exception as e:
                        logger.error(f"Failed to send weekly report: {e}")

            # ── Sleep for remainder of 1-minute cycle ──────────────────────────
            cycle_end  = datetime.now()
            elapsed    = (cycle_end - cycle_start).total_seconds()
            sleep_time = max(0, 60 - elapsed)
            logger.info(f"Cycle done in {elapsed:.1f}s. Sleeping {sleep_time:.1f}s...")
            try:
                refresh_report(days_back=30)
            except Exception as report_error:
                logger.error(f"Failed to refresh desktop trade report: {report_error}")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Bot manually stopped by user.")
        try:
            send_telegram_alert("🛑 <b>Bot Offline</b>\nAlphaEdge scanner manually shut down.")
        except Exception:
            pass
    except Exception as fatal_error:
        error_msg = (
            f"🚨 <b>CRITICAL BOT FAILURE</b> 🚨\n"
            f"The autonomous scanner has stopped!\nError: {fatal_error}"
        )
        logger.critical(error_msg)
        try:
            send_telegram_alert(error_msg)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
