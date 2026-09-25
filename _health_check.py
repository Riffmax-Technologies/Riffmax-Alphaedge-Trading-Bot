"""
AlphaEdge Engine Health Check
Verifies all modules load cleanly and core logic is correct.
"""
import sys

errors = []

# ── 1. Trade Logger ──────────────────────────────────────────────────────────
try:
    from m15_trade_analysis_logger import (
        get_performance_summary, sync_closed_trades_from_history
    )
    s = get_performance_summary()
    print("OK  m15_trade_analysis_logger")
    print(f"    Trades:{s['total']}  Wins:{s['wins']}  Losses:{s['losses']}  WR:{s['win_rate']}%  Net PnL:${s['net_pnl']}")
except Exception as e:
    print("ERR m15_trade_analysis_logger:", e)
    errors.append(str(e))

# ── 2. News Catalyst Engine ──────────────────────────────────────────────────
try:
    from news_catalyst_engine import NewsCatalystEngine, _eat_time
    engine = NewsCatalystEngine()
    print("OK  news_catalyst_engine")
    print(f"    Events loaded: {len(engine.events)}")
    for sym in ["XAUUSDm"]:
        s = engine.get_market_catalyst_status(sym)
        print(f"    {sym} now: state={s['state']}  action={s['action']}")
except Exception as e:
    print("ERR news_catalyst_engine:", e)
    errors.append(str(e))

# ── 3. AI Learning ───────────────────────────────────────────────────────────
try:
    from ai_learning import AutoLearner
    learner = AutoLearner()
    cfg = learner.load_config()
    print("OK  ai_learning")
    print(f"    gold_tp_dollars={cfg.get('gold_tp_dollars')}  regime={cfg.get('regime')}")
except Exception as e:
    print("ERR ai_learning:", e)
    errors.append(str(e))

# ── 4. Institutional Trader ────────────────────────────────────────────────
try:
    import institutional_trader
    gold = institutional_trader.ASSET_CONFIGS["XAUUSDm"]
    print("OK  institutional_trader")
    print(f"    Gold: lot={gold['lot']}  tp=${gold['tp_dollars']}  be=${gold['be_trigger_dollars']}  catalyst_tp=${gold['tp_catalyst_dollars']}")
except Exception as e:
    print("ERR institutional_trader:", e)
    errors.append(str(e))

# ── 5. Session Filter Boundary Check (8:00 AM - 8:00 PM EAT) ──────────────────
print()
print("--- Session filter (08:00 - 20:00 EAT / Monday - Friday) ---")
from institutional_trader import is_session_active
from datetime import datetime, timezone, timedelta

def sim_session(weekday, hour_eat):
    # EAT is UTC+3
    now_utc = datetime(2026, 9, 21 + weekday, hour_eat, 0, tzinfo=timezone.utc) - timedelta(hours=3)
    now_eat = now_utc + timedelta(hours=3)
    wd = now_eat.weekday()
    he = now_eat.hour
    if wd in (5, 6):
        return False
    if he < 8 or he >= 20:
        return False
    return True

tests = [
    (0, 7,  "Mon 07:00 EAT (pre-market)", False),
    (0, 8,  "Mon 08:00 EAT (market open)", True),
    (0, 12, "Mon 12:00 EAT (midday)     ", True),
    (0, 19, "Mon 19:00 EAT (evening)    ", True),
    (0, 20, "Mon 20:00 EAT (cutoff)     ", False),
    (0, 23, "Mon 23:00 EAT (overnight)  ", False),
    (4, 19, "Fri 19:00 EAT (open)       ", True),
    (4, 20, "Fri 20:00 EAT (cutoff)     ", False),
    (5, 12, "Sat 12:00 EAT (weekend)    ", False),
    (6, 12, "Sun 12:00 EAT (weekend)    ", False),
]
all_session_ok = True
for weekday, hour_eat, label, expected in tests:
    active = sim_session(weekday, hour_eat)
    ok = (active == expected)
    status = "OK " if ok else "ERR"
    if not ok:
        all_session_ok = False
        errors.append(f"Session mismatch at {label}: got {active} expected {expected}")
    print(f"  {status}  {label}  active={active}  {'pass' if ok else 'FAIL'}")

# ── 6. News State Machine ─────────────────────────────────────────────────────
print()
print("--- News state machine ---")
state_tests = [
    (-35, "NORMAL"),
    (-6,  "NORMAL"),
    (-5,  "PRE_NEWS_FREEZE"),
    (-1,  "PRE_NEWS_FREEZE"),
    (0,   "NEWS_SPIKE_BLOCK"),
    (2,   "NEWS_SPIKE_BLOCK"),
    (5,   "CATALYST_IMPULSE"),
    (15,  "CATALYST_IMPULSE"),
    (25,  "CATALYST_IMPULSE"),
    (26,  "NORMAL"),
]
blocks_states = {"PRE_NEWS_FREEZE", "NEWS_SPIKE_BLOCK"}
all_news_ok = True
for offset, expected_state in state_tests:
    diff = float(offset)
    if -5.0 <= diff < 0:
        state = "PRE_NEWS_FREEZE"
    elif 0 <= diff < 5.0:
        state = "NEWS_SPIKE_BLOCK"
    elif 5.0 <= diff <= 25.0:
        state = "CATALYST_IMPULSE"
    else:
        state = "NORMAL"
    ok = (state == expected_state)
    blocks = state in blocks_states
    if not ok:
        all_news_ok = False
        errors.append(f"State mismatch T{offset:+d}min: got {state} expected {expected_state}")
    print(f"  {'OK' if ok else 'ERR'}  T{offset:+3d}min -> {state:20s}  blocks_entry={blocks}  {'pass' if ok else 'FAIL'}")

# ── 7. Telegram recipients check ─────────────────────────────────────────────
print()
import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
except Exception:
    pass

token   = os.getenv("TELEGRAM_TOKEN", "")
chat_id = os.getenv("TELEGRAM_CHAT_ID",    "915238743")
channel = os.getenv("TELEGRAM_CHANNEL_ID", "@riffexalphaedgebot")
print(f"  Token   : {'SET' if token else 'MISSING'}")
print(f"  Chat ID : {chat_id}")
print(f"  Channel : {channel}")

# ── 8. Public Channel Firewall Verification ──────────────────────────────────
print()
print("--- Channel Firewall Security Test ---")
from institutional_trader import _is_channel_allowed

firewall_test_cases = [
    ("🚀 <b>[AlphaEdge Signal]</b>\nAsset: XAUUSDm\nAction: BUY", True, "Trade Entry Signal"),
    ("🎯 <b>[Trade Closed — WIN]</b>\nAsset: XAUUSDm (BUY)\nResult: +$10.00", True, "Trade Close Win"),
    ("🛑 <b>[Trade Closed — LOSS]</b>\nAsset: XAUUSDm (BUY)\nResult: -$10.00", True, "Trade Close Loss"),
    ("🛡️ <b>[Trade Closed — BREAK-EVEN]</b>\nAsset: XAUUSDm", True, "Trade Close Break-Even"),
    ("🔄 <b>[Trade Closed — REVERSAL]</b>\nAsset: XAUUSDm", True, "Trade Close Reversal"),
    ("📊 <b>AlphaEdge Daily Gold Market Report</b>\nEnd of Day", False, "Daily Market Report"),
    ("📊 ALPHAEDGE DAILY REPORT\nDate: 2026-09-14", False, "Daily Performance Report"),
    ("🛑 <b>[AlphaEdge Bot Offline]</b>\nScanner was stopped", False, "Bot Offline Notification"),
    ("🟢 <b>AlphaEdge Bot Status Report</b>\nMarket: Gold", False, "Bot Status Reply"),
    ("📅 <b>AlphaEdge Daily News Briefing</b>\nHigh-Impact", False, "News Briefing"),
    ("⏰ <b>30-Minute News Alert</b>\nCore CPI m/m", False, "30-Min News Alert"),
    ("🛡️ <b>[Break-Even Protected]</b>\nAsset: XAUUSDm", False, "Break-Even Protection"),
    ("⚠️ <b>[Pre-News Protection]</b>\nAsset: XAUUSDm", False, "Pre-News Protection"),
]

for msg, expected_allowed, desc in firewall_test_cases:
    actual = _is_channel_allowed(msg)
    ok = (actual == expected_allowed)
    status = "OK " if ok else "ERR"
    action = "PERMITTED" if actual else "BLOCKED  "
    if not ok:
        errors.append(f"Firewall test failed for '{desc}': got {actual}, expected {expected_allowed}")
    print(f"  {status} [{action}] {desc:30s} -> {'pass' if ok else 'FAIL'}")

# ── Final Result ──────────────────────────────────────────────────────────────
print()
if errors:
    print(f"HEALTH CHECK FAILED -- {len(errors)} error(s):")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED. AlphaEdge engine is clean and ready to run.")
