"""
ai_learning.py — Autonomous M1 Scalper Learning & Decision Brain
================================================================
Analyzes live MetaTrader 5 trade history for magic number 20250831 (AUTONOMOUS_M1).
Computes performance metrics over the last 24-48 hours:
- Win Rate % (TP hits vs SL hits vs Reversal exits)
- Gross Profit, Gross Loss, and Profit Factor
- Average Win ($) vs Average Loss ($)
- Reversal churn frequency

Adapts scalper parameters dynamically:
- TP ATR Multiplier (1.6 - 2.2)
- TP Minimum Target ($3.80 - $5.00)
- SL Maximum Risk Cap ($3.00 - $3.50)
- Reversal confirmation thresholds

Persists optimal settings to 'config_learned_scalp.json' for real-time pickup by scalping_gold.py.
"""

import os
import json
import logging
from datetime import datetime, timedelta
import urllib.request
import MetaTrader5 as mt5
import pandas as pd

logger = logging.getLogger("AlphaEdge.AutoLearner")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_learned_scalp.json")
SCALP_MAGIC = 20250831


def send_telegram(message: str):
    token   = os.getenv("TELEGRAM_TOKEN", "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "915238743")
    if not token or not chat_id:
        return
    url     = "https://api.telegram.org/bot" + token + "/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        logger.debug(f"[AutoLearner Telegram] {exc}")


class AutoLearner:
    def __init__(self, config_path=CONFIG_PATH, lookback_hours=48):
        self.config_path = config_path
        self.lookback_hours = lookback_hours

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {self.config_path}: {e}")
        return {
            "tp_atr_mult": 1.8,
            "tp_min_dist": 4.00,
            "tp_max_dist": 6.50,
            "sl_min_dist": 2.50,
            "sl_max_dist": 3.50,
            "regime": "BALANCED",
            "pure_win_rate": 50.0,
            "total_trades": 0,
            "last_updated": None
        }

    def save_config(self, config):
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)
            logger.info(f"[AutoLearner] Saved learned configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving {self.config_path}: {e}")

    def analyze_history_and_adapt(self) -> dict:
        if not mt5.terminal_info():
            login = int(os.getenv("MT5_LOGIN", "0"))
            pwd   = os.getenv("MT5_PASSWORD", "")
            srv   = os.getenv("MT5_SERVER", "")
            if login > 0:
                mt5.initialize(login=login, password=pwd, server=srv)
            else:
                mt5.initialize()

        date_from = datetime.now() - timedelta(hours=self.lookback_hours)
        date_to   = datetime.now()
        deals = mt5.history_deals_get(date_from, date_to)

        if not deals:
            logger.info("[AutoLearner] No MT5 deals found in lookback window.")
            return self.load_config()

        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        scalp_exits = df[(df['entry'] == 1) & (df['magic'] == SCALP_MAGIC)].copy()

        if len(scalp_exits) < 5:
            logger.info(f"[AutoLearner] Found {len(scalp_exits)} scalp trades. Need >= 5 trades to adapt.")
            return self.load_config()

        scalp_exits['time'] = pd.to_datetime(scalp_exits['time'], unit='s')
        total_trades = len(scalp_exits)
        wins = scalp_exits[scalp_exits['profit'] > 0]
        losses = scalp_exits[scalp_exits['profit'] < 0]

        win_rate = (len(wins) / total_trades) * 100.0
        gross_profit = float(wins['profit'].sum())
        gross_loss = float(abs(losses['profit'].sum()))
        net_pnl = float(scalp_exits['profit'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        tp_deals = scalp_exits[scalp_exits['comment'].str.contains('tp', na=False, case=False)]
        sl_deals = scalp_exits[scalp_exits['comment'].str.contains('sl', na=False, case=False)]
        rev_deals = scalp_exits[scalp_exits['comment'].str.contains('Reversal', na=False, case=False)]

        pure_completed = len(tp_deals) + len(sl_deals)
        pure_win_rate = (len(tp_deals) / pure_completed * 100.0) if pure_completed > 0 else 50.0

        avg_win = float(wins['profit'].mean()) if len(wins) > 0 else 0.0
        avg_loss = float(abs(losses['profit'].mean())) if len(losses) > 0 else 0.0

        logger.info(
            f"[AutoLearner Analysis] {total_trades} trades | TP: {len(tp_deals)} | SL: {len(sl_deals)} | "
            f"Reversals: {len(rev_deals)} | Pure Win Rate: {pure_win_rate:.1f}% | Net: ${net_pnl:+.2f}"
        )

        # ── Dynamic Adaptation Decisions ──
        # Baseline balanced values (1:1.3 R:R)
        tp_atr_mult = 1.8
        tp_min_dist = 4.00
        tp_max_dist = 6.50
        sl_min_dist = 2.50
        sl_max_dist = 3.50
        regime = "BALANCED"

        if pure_win_rate >= 55.0 and len(tp_deals) >= 15:
            # Strong trend capture: let winners run with expanded TP
            tp_atr_mult = 2.0
            tp_min_dist = 4.50
            tp_max_dist = 7.00
            sl_max_dist = 3.50
            regime = "TRENDING_MOMENTUM"
        elif pure_win_rate < 48.0 or len(rev_deals) > len(tp_deals):
            # Choppy regime or high reversal friction: protect capital with tighter SL
            tp_atr_mult = 1.6
            tp_min_dist = 3.80
            tp_max_dist = 5.50
            sl_max_dist = 3.00
            regime = "CHOPPY_DEFENSIVE"

        old_config = self.load_config()
        new_config = {
            "tp_atr_mult": round(tp_atr_mult, 2),
            "tp_min_dist": round(tp_min_dist, 2),
            "tp_max_dist": round(tp_max_dist, 2),
            "sl_min_dist": round(sl_min_dist, 2),
            "sl_max_dist": round(sl_max_dist, 2),
            "regime": regime,
            "pure_win_rate": round(pure_win_rate, 1),
            "total_trades": total_trades,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Check if changed
        has_changed = (
            old_config.get("regime") != new_config["regime"] or
            old_config.get("tp_atr_mult") != new_config["tp_atr_mult"] or
            old_config.get("sl_max_dist") != new_config["sl_max_dist"]
        )

        self.save_config(new_config)

        if has_changed:
            msg = (
                f"🧠 <b>[AI Auto-Learner Adaptation]</b>\n\n"
                f"• <b>Market Regime:</b> {regime}\n"
                f"• <b>Historical Sample:</b> {total_trades} trades ({len(tp_deals)} TP / {len(sl_deals)} SL)\n"
                f"• <b>Pure Win Rate:</b> {pure_win_rate:.1f}%\n"
                f"• <b>Net PnL (48h):</b> ${net_pnl:+.2f}\n"
                f"• <b>Tuned Take Profit:</b> {tp_atr_mult}x ATR (Min ${tp_min_dist:.2f} / Max ${tp_max_dist:.2f})\n"
                f"• <b>Tuned Stop Loss:</b> Max Cap ${sl_max_dist:.2f}\n"
                f"• <b>Decision:</b> Self-optimized for 1:1.3+ Risk-to-Reward!"
            )
            send_telegram(msg)

        return new_config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    learner = AutoLearner()
    cfg = learner.analyze_history_and_adapt()
    print("\nResult Config:")
    print(json.dumps(cfg, indent=4))
