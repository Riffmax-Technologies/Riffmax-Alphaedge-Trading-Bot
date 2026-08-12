"""Test MT5 connection and place a tiny test market order.
Reads credentials from local .env and uses the metatrader_client shim.
"""
import os
import time
from datetime import datetime
import MetaTrader5 as mt5
from metatrader_client import MT5Client
import sys
import os
# Ensure .agents is importable like other modules in the project
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
agents_path = os.path.join(PROJECT_ROOT, '.agents')
if agents_path not in sys.path:
    sys.path.insert(0, agents_path)
from trading_bot_skills.trade_config import TELEGRAM_ENABLED


def load_env(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def send_telegram_message(msg: str):
    try:
        from alphaedge import send_telegram_alert
        send_telegram_alert(msg)
    except Exception:
        pass


def main():
    load_env('.env')
    config = {
        'login': int(os.environ.get('MT5_LOGIN', 0)),
        'password': os.environ.get('MT5_PASSWORD', ''),
        'server': os.environ.get('MT5_SERVER', ''),
    }
    client = MT5Client(config)
    try:
        client.connect()
    except Exception as e:
        print(f"MT5 connect failed: {e}")
        return

    account = mt5.account_info()
    print(f"Connected. Account: {getattr(account, 'login', 'N/A')} Balance: {getattr(account, 'balance', 0.0)}")

    # Choose a safe symbol: prefer EURUSD if available
    symbol = 'EURUSD'
    if not mt5.symbol_select(symbol, True):
        symbols = [s.name for s in mt5.symbols_get() if s.visible]
        symbol = symbols[0] if symbols else None

    if not symbol:
        print("No tradable symbol available to test.")
        client.disconnect()
        return

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print("Failed to get tick for symbol.")
        client.disconnect()
        return

    price = tick.ask
    info = mt5.symbol_info(symbol)
    volume = info.volume_min if info and info.volume_min else 0.01

    # Place a tiny market BUY order with conservative SL/TP
    point = info.point if info else 0.00001
    stops_level = getattr(info, 'stops_level', None) or getattr(info, 'trade_stops_level', None) or 0
    min_stop_pts = max(50, int(stops_level) + 5)
    sl = round(price - min_stop_pts * point, 5)
    tp = round(price + (min_stop_pts * 2) * point, 5)

    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_BUY,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 10,
        'comment': 'TEST_ORDER',
        'type_filling': mt5.ORDER_FILLING_FOK if hasattr(mt5, 'ORDER_FILLING_FOK') else 0,
    }

    print(f"Sending test order: {symbol} {volume} @ {price:.5f} SL {sl} TP {tp}")
    res = mt5.order_send(request)
    if res and getattr(res, 'retcode', None) == mt5.TRADE_RETCODE_DONE:
        msg = f"✅ Test order placed: {symbol} {volume} @ {price:.5f} (Ticket: {getattr(res, 'order', 'N/A')})"
        print(msg)
        if TELEGRAM_ENABLED:
            send_telegram_message(msg)
    else:
        print(f"Test order failed: {getattr(res, 'comment', getattr(res, 'retcode', res))}")
    client.disconnect()


if __name__ == '__main__':
    main()
