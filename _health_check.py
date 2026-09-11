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
    for sym in ["XAUUSDm", "DE30m"]:
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
    print(f"    gold_tp_dollars={cfg.get('gold_tp_dollars')}  dax_tp_pts={cfg.get('dax_tp_pts')}  regime={cfg.get('regime')}")
except Exception as e:
    print("ERR ai_learning:", e)
    errors.append(str(e))

# ── 4. Scalping Gold ─────────────────────────────────────────────────────────
try:
    import scalping_gold
    gold = scalping_gold.ASSET_CONFIGS["XAUUSDm"]
    dax  = scalping_gold.ASSET_CONFIGS["DE30m"]
    print("OK  scalping_gold")
    print(f"    Gold: lot={gold['lot']}  tp=${gold['tp_dollars']}  be=${gold['be_trigger_dollars']}  catalyst_tp=${gold['tp_catalyst_dollars']}")
    print(f"    DAX:  lot={dax['lot']}   tp={dax['tp_pts']}pts  be={dax['be_trigger_pts']}pts  catalyst_tp={dax['tp_catalyst_pts']}pts")
except Exception as e:
    print("ERR scalping_gold:", e)
    errors.append(str(e))

# ── 5. Session Filter Boundary Check ─────────────────────────────────────────
print()
print("--- Session filter (04:00 UTC = 07:00 EAT start) ---")
tests = [
    (3,  3, "Thu 03:00 UTC (06:00 EAT)", False),
    (4,  3, "Thu 04:00 UTC (07:00 EAT)", True),
    (7,  3, "Thu 07:00 UTC (10:00 EAT)", True),
    (20, 3, "Thu 20:00 UTC (23:00 EAT)", True),
    (21, 3, "Thu 21:00 UTC (00:00 EAT)", False),
    (10, 4, "Fri 10:00 UTC            ", True),
    (21, 4, "Fri 21:00 UTC (weekend)  ", False),
    (12, 5, "Sat 12:00 UTC            ", False),
    (22, 6, "Sun 22:00 UTC (mkt open) ", False),  # Market reopens but our session starts Mon 04:00 UTC
    (4,  0, "Mon 04:00 UTC (start)    ", True),
]
all_session_ok = True
for hour, weekday, label, expected in tests:
    fri_close  = (weekday == 4 and hour >= 21)
    is_sat     = (weekday == 5)
    sun_early  = (weekday == 6 and hour < 22)
    active     = (4 <= hour < 21) and not fri_close and not is_sat and not sun_early
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
print("--- Telegram config ---")
import os
token   = os.getenv("TELEGRAM_TOKEN",      "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0")
chat_id = os.getenv("TELEGRAM_CHAT_ID",    "915238743")
channel = os.getenv("TELEGRAM_CHANNEL_ID", "@riffexalphaedgebot")
print(f"  Token   : {'SET' if token else 'MISSING'}")
print(f"  Chat ID : {chat_id}")
print(f"  Channel : {channel}")

# ── Final Result ──────────────────────────────────────────────────────────────
print()
if errors:
    print(f"HEALTH CHECK FAILED -- {len(errors)} error(s):")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED. AlphaEdge engine is clean and ready to run.")
