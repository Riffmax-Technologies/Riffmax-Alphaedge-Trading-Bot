import MetaTrader5 as mt5
from datetime import datetime, timedelta

import os

MT5_CONFIG = {
    'login': int(os.getenv('MT5_LOGIN', '0')),
    'password': os.getenv('MT5_PASSWORD', ''),
    'server': os.getenv('MT5_SERVER', '')
}

ok = mt5.initialize(login=MT5_CONFIG['login'], password=MT5_CONFIG['password'], server=MT5_CONFIG['server'])
if not ok:
    print('MT5 init failed', mt5.last_error())
    raise SystemExit(1)

now = datetime.now()
start = now - timedelta(days=365)
deals = mt5.history_deals_get(start, now)
if not deals:
    print('No deals returned')
else:
    first = deals[0]
    try:
        d = first._asdict()
        print('deal fields:', list(d.keys()))
    except Exception:
        # fallback: dir
        print('deal dir:', dir(first))

mt5.shutdown()
