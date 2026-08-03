# telegram_bot.py
"""Telegram bot for AlphaEdge trading bot.
Provides simple commands to check status, trigger a manual scan, place a manual trade,
view open positions and P&L.
The bot uses the token defined in `trade_config.py` and restricts usage to the
configured chat ID for safety.
"""

import logging
import os
from pathlib import Path
import json
import traceback

import MetaTrader5 as mt5
from telegram import Update, BotCommand
from telegram.ext import Updater, CommandHandler, CallbackContext

# Load configuration
from .trade_config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    MT5_PATH,
    EXNESS_CONFIG,
    DERIV_CONFIG,
    USE_DERIV,
    DAILY_PNL_PATH,
)

# Configure logging
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Helper to ensure MT5 is initialized with the correct broker
def init_mt5():
    config = DERIV_CONFIG if USE_DERIV else EXNESS_CONFIG
    init_kwargs = {
        "login": config["login"],
        "password": config["password"],
        "server": config["server"],
    }
    if USE_DERIV and MT5_PATH:
        init_kwargs["path"] = MT5_PATH
    mt5.shutdown()
    ok = mt5.initialize(**init_kwargs)
    if not ok:
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    return ok

# /status – basic health check
def status(update: Update, context: CallbackContext):
    try:
        update.message.reply_text("🤖 AlphaEdge bot is online and ready.")
    except Exception as e:
        logger.error(f"Status command error: {e}")
        update.message.reply_text("❗ Error retrieving status.")

# /scan – trigger a manual AlphaEdge scan
def scan(update: Update, context: CallbackContext):
    try:
        # Import the AlphaEdge scan function lazily to avoid heavy imports at start‑up
        from alphaedge import run_alphaedge
        update.message.reply_text("🔎 Running manual scan…")
        run_alphaedge()
        update.message.reply_text("✅ Scan completed.")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Scan command failed: {e}\n{tb}")
        update.message.reply_text(f"❗ Scan failed: {e}")

# /trade <symbol> <volume> <type>
# type = BUY or SELL (case‑insensitive)
def trade(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 3:
            update.message.reply_text("Usage: /trade <symbol> <volume> <BUY|SELL>")
            return
        symbol, volume_str, order_type = args
        volume = float(volume_str)
        order_type = order_type.upper()
        if order_type not in ("BUY", "SELL"):
            update.message.reply_text("Order type must be BUY or SELL.")
            return
        init_mt5()
        info = mt5.symbol_info(symbol)
        if not info:
            update.message.reply_text(f"Symbol {symbol} not found.")
            return
        if not info.visible:
            mt5.symbol_select(symbol, True)
        price = mt5.symbol_info_tick(symbol).ask if order_type == "BUY" else mt5.symbol_info_tick(symbol).bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "AlphaEdge_manual",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            update.message.reply_text(f"✅ {order_type} order placed on {symbol} – Ticket {result.order}")
        else:
            err = result.comment if result else "N/A"
            ret = result.retcode if result else "N/A"
            update.message.reply_text(f"❗ Trade failed: {err} (Retcode: {ret})")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Trade command error: {e}\n{tb}")
        update.message.reply_text(f"❗ Error placing trade: {e}")
    finally:
        mt5.shutdown()

# /positions – list open positions
def positions(update: Update, context: CallbackContext):
    try:
        init_mt5()
        pos = mt5.positions_get()
        if not pos:
            update.message.reply_text("No open positions.")
            return
        lines = []
        for p in pos:
            lines.append(
                f"{p.ticket}: {p.symbol} {p.type} {p.volume}@{p.price} SL={p.sl} TP={p.tp} Profit={p.profit}"
            )
        msg = "📊 Open positions:\n" + "\n".join(lines)
        update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Positions command error: {e}")
        update.message.reply_text(f"❗ Failed to fetch positions: {e}")
    finally:
        mt5.shutdown()

# /pnl – show today's P&L from the daily JSON file
def pnl(update: Update, context: CallbackContext):
    try:
        if DAILY_PNL_PATH.is_file():
            data = json.loads(DAILY_PNL_PATH.read_text())
            profit = data.get("profit", 0)
            loss = data.get("loss", 0)
            update.message.reply_text(f"📈 Today P&L – Profit: {profit:.2f}, Loss: {loss:.2f}")
        else:
            update.message.reply_text("Daily P&L file not found.")
    except Exception as e:
        logger.error(f"PNL command error: {e}")
        update.message.reply_text(f"❗ Error reading P&L: {e}")

def main():
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token not set in trade_config.py")
        return
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Restrict to the configured chat ID – simple check in each handler
    def chat_filter(func):
        def wrapper(update: Update, context: CallbackContext):
            if str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
                update.message.reply_text("❌ Unauthorized user.")
                return
            return func(update, context)
        return wrapper

    dp.add_handler(CommandHandler("status", chat_filter(status)))
    dp.add_handler(CommandHandler("scan", chat_filter(scan)))
    dp.add_handler(CommandHandler("trade", chat_filter(trade)))
    dp.add_handler(CommandHandler("positions", chat_filter(positions)))
    dp.add_handler(CommandHandler("pnl", chat_filter(pnl)))

    # Set command list for user convenience
    commands = [
        BotCommand("status", "Bot health check"),
        BotCommand("scan", "Run manual AlphaEdge scan"),
        BotCommand("trade", "Place manual trade: /trade <symbol> <volume> <BUY|SELL>"),
        BotCommand("positions", "List open positions"),
        BotCommand("pnl", "Show today P&L"),
    ]
    updater.bot.set_my_commands(commands)

    logger.info("Starting Telegram bot…")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
