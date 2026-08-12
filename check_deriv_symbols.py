# check_deriv_symbols.py – verify which symbols exist on the Deriv-Demo account
import MetaTrader5 as mt5
import os, sys

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

MT5_CONFIG = {
    "login": int(os.environ["MT5_LOGIN"]),
    "password": os.environ["MT5_PASSWORD"],
    "server": os.environ["MT5_SERVER"],
}

if not mt5.initialize(login=MT5_CONFIG["login"], password=MT5_CONFIG["password"], server=MT5_CONFIG["server"]):
    print(f"Failed to initialize MT5: {mt5.last_error()}")
    sys.exit(1)

print(f"Connected to {MT5_CONFIG['server']} (login {MT5_CONFIG['login']})")

# Check our 15 target symbols
targets = [
    "BTCUSD", "ETHUSD", "XAUUSD", "USOIL", "US30", "NAS100",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY"
]

print("\n=== Checking our 15 target symbols ===")
for sym in targets:
    info = mt5.symbol_info(sym)
    if info:
        print(f"  OK  {sym} (spread={info.spread}, filling_mode={info.filling_mode}, visible={info.visible})")
    else:
        print(f"  MISSING  {sym}")

# Also search for similar names (Deriv might use different names)
print("\n=== Searching for Oil/Energy symbols ===")
oil_syms = mt5.symbols_get("*OIL*") or []
for s in oil_syms:
    print(f"  {s.name}")
oil_syms2 = mt5.symbols_get("*WTI*") or []
for s in oil_syms2:
    print(f"  {s.name}")
oil_syms3 = mt5.symbols_get("*CL*") or []
for s in oil_syms3:
    print(f"  {s.name}")

print("\n=== Searching for Index symbols ===")
idx_syms = mt5.symbols_get("*US30*") or []
for s in idx_syms:
    print(f"  {s.name}")
idx_syms2 = mt5.symbols_get("*NAS*") or []
for s in idx_syms2:
    print(f"  {s.name}")
idx_syms3 = mt5.symbols_get("*DOW*") or []
for s in idx_syms3:
    print(f"  {s.name}")
idx_syms4 = mt5.symbols_get("*DJ*") or []
for s in idx_syms4:
    print(f"  {s.name}")

print("\n=== All available symbols (first 100) ===")
all_syms = mt5.symbols_get() or []
print(f"Total symbols: {len(all_syms)}")
for s in sorted(all_syms, key=lambda x: x.name)[:100]:
    print(f"  {s.name}")

mt5.shutdown()
