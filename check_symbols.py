#!/usr/bin/env python3
import os
import MetaTrader5 as mt5
import alphaedge

cand = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURGBP","EURJPY","EURAUD","GBPJPY","GBPAUD","DE30","US30","USTEC",
    "US500","USOIL","UKOIL","XAUUSD","XAGUSD","WTICOUSD","BTCUSD","ETHUSD",
    "SOLUSD","XRPUSD","LTCUSD","ADAUSD","DOGEUSD","SPX500","JP225","CN50"
]

if not mt5.initialize(login=alphaedge.MT5_CONFIG['login'], password=alphaedge.MT5_CONFIG['password'], server=alphaedge.MT5_CONFIG['server']):
    print('MT5 init failed:', mt5.last_error())
    raise SystemExit(1)

tradable = []
for s in cand:
    info = mt5.symbol_info(s)
    if info is None:
        print(f"{s}: not found on broker")
        continue
    # visible and trade allowed
    visible = getattr(info, 'visible', True)
    trade_mode = getattr(info, 'trade_mode', None)
    if not visible:
        print(f"{s}: not visible")
        continue
    # consider tradable if symbol_info exists and is visible
    print(f"{s}: tradable (point={getattr(info,'point',None)}, digits={getattr(info,'digits',None)})")
    tradable.append(s)

mt5.shutdown()
print('\nTradable symbols:')
print(tradable)
with open('tradable_symbols.txt','w',encoding='utf-8') as f:
    for s in tradable:
        f.write(s + "\n")
print('\nWrote tradable_symbols.txt')
