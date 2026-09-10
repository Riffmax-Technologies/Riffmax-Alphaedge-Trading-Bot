"""
AlphaEdge Telegram Command Listener
====================================
Paste commands in your Telegram chat to control the bot:

  /status    — Account balance, equity, open trades
  /positions — List all open trades with PnL
  /pause     — Pause new entries (existing trades still managed)
  /resume    — Resume normal trading
  /closeall  — Emergency close ALL open positions immediately
"""
import urllib.request
import json
import MetaTrader5 as mt5

TELEGRAM_TOKEN   = "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0"
TELEGRAM_CHAT_ID = "915238743"

BOT_PAUSED     = False
LAST_UPDATE_ID = 0


def _post(text: str):
    payload = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def poll_telegram_commands(logger=None):
    global BOT_PAUSED, LAST_UPDATE_ID

    try:
        url = (
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
            f"/getUpdates?offset={LAST_UPDATE_ID + 1}&timeout=2"
        )
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read())

        if not data.get("ok"):
            return BOT_PAUSED

        for update in data.get("result", []):
            LAST_UPDATE_ID = update["update_id"]
            msg     = update.get("message") or {}
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text    = msg.get("text", "").strip().lower()

            if chat_id != TELEGRAM_CHAT_ID:
                continue

            if text == "/status":
                account   = mt5.account_info()
                positions = mt5.positions_get() or []
                bal    = account.balance if account else 0.0
                equity = account.equity  if account else 0.0
                state  = "PAUSED" if BOT_PAUSED else "ACTIVE"
                _post(
                    "<b>AlphaEdge Status</b>\n"
                    f"Balance:     <b>${bal:.2f}</b>\n"
                    f"Equity:      <b>${equity:.2f}</b>\n"
                    f"Open Trades: <b>{len(positions)}</b>\n"
                    f"Bot State:   <b>{state}</b>\n"
                    "Assets: XAUUSDz | GBPUSDz | US30z | EURJPYz"
                )

            elif text == "/positions":
                positions = mt5.positions_get() or []
                if not positions:
                    _post("No open positions currently.")
                else:
                    lines = ["<b>Open Positions:</b>"]
                    for p in positions:
                        direction = "BUY" if p.type == 0 else "SELL"
                        lines.append(
                            f"{p.symbol} {direction} | "
                            f"PnL: ${p.profit:.2f} | "
                            f"SL: {p.sl:.5f} | TP: {p.tp:.5f}"
                        )
                    _post("\n".join(lines))

            elif text == "/pause":
                BOT_PAUSED = True
                _post("<b>Bot PAUSED.</b> No new trades will be opened.\nExisting trades are still being managed.")
                if logger:
                    logger.info("[Telegram CMD] Bot paused by user.")

            elif text == "/resume":
                BOT_PAUSED = False
                _post("<b>Bot RESUMED.</b> Scanning and trading normally.")
                if logger:
                    logger.info("[Telegram CMD] Bot resumed by user.")

            elif text == "/closeall":
                _post("<b>EMERGENCY CLOSE ALL</b> — Closing all positions now...")
                positions = mt5.positions_get() or []
                closed = 0
                for pos in positions:
                    tick = mt5.symbol_info_tick(pos.symbol)
                    if not tick:
                        continue
                    close_type  = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                    close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                    req = {
                        "action":       mt5.TRADE_ACTION_DEAL,
                        "symbol":       pos.symbol,
                        "volume":       pos.volume,
                        "type":         close_type,
                        "position":     pos.ticket,
                        "price":        close_price,
                        "deviation":    30,
                        "comment":      "TG_CloseAll",
                        "type_time":    mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    res = mt5.order_send(req)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        closed += 1
                _post(f"Closed <b>{closed}</b> position(s) successfully.")
                if logger:
                    logger.info(f"[Telegram CMD] Emergency closed {closed} positions.")

            elif text.startswith("/"):
                _post(
                    "<b>AlphaEdge Commands:</b>\n"
                    "/status    - Account summary\n"
                    "/positions - Open trades\n"
                    "/pause     - Pause new entries\n"
                    "/resume    - Resume trading\n"
                    "/closeall  - Emergency close all"
                )

    except Exception as e:
        if logger:
            logger.warning(f"[Telegram CMD] Poll error: {e}")

    return BOT_PAUSED
