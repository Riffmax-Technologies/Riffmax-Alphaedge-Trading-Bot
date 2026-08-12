# telegram_bot.py
"""Telegram bot for AlphaEdge trading bot.
Provides simple commands to check status, trigger a manual scan, place a manual trade,
view open positions and P&L.
The bot uses python‑telegram‑bot v20 (ApplicationBuilder) for compatibility.
"""

import logging
import json
import traceback
import asyncio
import os
from pathlib import Path

import MetaTrader5 as mt5
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.is_file():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# Configure logging
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Helper to ensure MT5 is initialized with the correct broker
def init_mt5():
    init_kwargs = {
        "login": MT5_LOGIN,
        "password": MT5_PASSWORD,
        "server": MT5_SERVER,
    }
    mt5.shutdown()
    ok = mt5.initialize(**init_kwargs)
    if not ok:
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    return ok

# Helper to restrict to configured chat
async def chat_filter(update: Update, context: ContextTypes.DEFAULT_TYPE, func):
    if str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    return await func(update, context)

# /status – basic health check
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _status)

async def _status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🤖 AlphaEdge bot is online and ready.")
    except Exception as e:
        logger.error(f"Status command error: {e}")
        await update.message.reply_text("❗ Error retrieving status.")

# /scan – trigger a manual AlphaEdge scan
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _scan)

async def _scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from alphaedge import run_alphaedge
        from datetime import datetime, timezone, timedelta
        
        init_mt5()
        account_info = mt5.account_info()
        
        if account_info:
            balance = account_info.balance
            equity = account_info.equity
            drawdown = max(0, balance - equity)
            
            # Calculate today's profit
            now = datetime.now()
            start_of_day = datetime(now.year, now.month, now.day)
            deals = mt5.history_deals_get(start_of_day, now + timedelta(days=1))
            today_profit = 0.0
            if deals:
                for deal in deals:
                    if deal.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                        today_profit += deal.profit
            
            msg = (
                f"🔎 <b>Running Manual Scan...</b>\n\n"
                f"💼 <b>Account Overview:</b>\n"
                f"Balance: ${balance:,.2f}\n"
                f"Equity: ${equity:,.2f}\n"
                f"Drawdown: ${drawdown:,.2f}\n"
                f"Today's Profit: ${today_profit:,.2f}"
            )
        else:
            msg = "🔎 <b>Running Manual Scan...</b>\n(Unable to retrieve account info)"
            
        await update.message.reply_text(msg, parse_mode='HTML')
        
        # run_alphaedge may be synchronous; run in thread
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_alphaedge)
        await update.message.reply_text("✅ Scan completed.")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Scan command failed: {e}\n{tb}")
        await update.message.reply_text(f"❗ Scan failed: {e}")

# /trade <symbol> <volume> <BUY|SELL>
async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _trade)

async def _trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text("Usage: /trade <symbol> <volume> <BUY|SELL>")
            return
        symbol, volume_str, order_type = args
        volume = float(volume_str)
        order_type = order_type.upper()
        if order_type not in ("BUY", "SELL"):
            await update.message.reply_text("Order type must be BUY or SELL.")
            return
        init_mt5()
        info = mt5.symbol_info(symbol)
        if not info:
            await update.message.reply_text(f"Symbol {symbol} not found.")
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
            await update.message.reply_text(f"✅ {order_type} order placed on {symbol} – Ticket {result.order}")
        else:
            err = result.comment if result else "N/A"
            ret = result.retcode if result else "N/A"
            await update.message.reply_text(f"❗ Trade failed: {err} (Retcode: {ret})")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Trade command error: {e}\n{tb}")
        await update.message.reply_text(f"❗ Error placing trade: {e}")
    finally:
        mt5.shutdown()

# /positions – list open positions
async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _positions)

async def _positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        init_mt5()
        pos = mt5.positions_get()
        if not pos:
            await update.message.reply_text("No open positions.")
            return
        lines = []
        for p in pos:
            lines.append(
                f"{p.ticket}: {p.symbol} {p.type} {p.volume}@{p.price} SL={p.sl} TP={p.tp} Profit={p.profit}"
            )
        msg = "📊 Open positions:\n" + "\n".join(lines)
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Positions command error: {e}")
        await update.message.reply_text(f"❗ Failed to fetch positions: {e}")
    finally:
        mt5.shutdown()

# /pnl – show today's P&L
async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _pnl)

async def _pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if DAILY_PNL_PATH.is_file():
            data = json.loads(DAILY_PNL_PATH.read_text())
            profit = data.get("profit", 0)
            loss = data.get("loss", 0)
            await update.message.reply_text(f"📈 Today P&L – Profit: {profit:.2f}, Loss: {loss:.2f}")
        else:
            await update.message.reply_text("Daily P&L file not found.")
    except Exception as e:
        logger.error(f"PNL command error: {e}")
        await update.message.reply_text(f"❗ Error reading P&L: {e}")

# Remote Control Commands
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _start_cmd)

async def _start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>AlphaEdge Bot Controller</b>\n\n"
        "Available Commands:\n"
        "/status - Check bot health\n"
        "/scan - Force a manual scan immediately\n"
        "/positions - View open positions\n"
        "/pnl - View today's profit\n"
        "/start_scanner - Resume the autonomous 5-min scanner\n"
        "/stop_scanner - Pause the autonomous 5-min scanner\n"
    )
    await update.message.reply_text(msg, parse_mode='HTML')

async def start_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _start_scanner)
    
async def _start_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    Path("bot_state.txt").write_text("RUNNING")
    await update.message.reply_text("▶️ <b>Scanner Resumed</b>\nThe autonomous 5-minute scan cycle is now active.", parse_mode='HTML')
    
async def stop_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat_filter(update, context, _stop_scanner)
    
async def _stop_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    Path("bot_state.txt").write_text("STOPPED")
    await update.message.reply_text("⏸️ <b>Scanner Paused</b>\nThe autonomous scanner will skip cycles until resumed.", parse_mode='HTML')

async def main():
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token not set in .env")
        return
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Register handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("start_scanner", start_scanner))
    application.add_handler(CommandHandler("stop_scanner", stop_scanner))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("scan", scan))
    application.add_handler(CommandHandler("trade", trade))
    application.add_handler(CommandHandler("positions", positions))
    application.add_handler(CommandHandler("pnl", pnl))
    # Set commands for UI
    commands = [
        BotCommand("start", "Show command menu"),
        BotCommand("start_scanner", "Resume autonomous scanning"),
        BotCommand("stop_scanner", "Pause autonomous scanning"),
        BotCommand("status", "Bot health check"),
        BotCommand("scan", "Run manual AlphaEdge scan"),
        BotCommand("trade", "Place manual trade: /trade <symbol> <volume> <BUY|SELL>"),
        BotCommand("positions", "List open positions"),
        BotCommand("pnl", "Show today P&L"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Starting Telegram bot…")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
