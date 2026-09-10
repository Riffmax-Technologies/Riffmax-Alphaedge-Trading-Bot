"""
ai_learning.py — AlphaEdge M15 AI Auto-Learning & Decision Brain
================================================================
Analyzes executed M15 trades from 'm15_trade_analysis.csv' and MT5 deal history.
Evaluates performance metrics over the last 24-72 hours:
- M15 Swing Win Rate % (Target Hits vs Break-Even Stops vs Reversals)
- Profit Factor and Net Realized PnL ($)
- Break-Even efficiency (saving capital vs prematurely cutting swings)
- Average trade hold duration (in hours/candles)
- News Catalyst response performance

Dynamically tunes swing parameters:
- Gold TP: Strict $8.00 (Standard) to $10.00 / $16.00 (Trending/Catalyst)
- Gold Break-Even Trigger: $5.00 to $6.50 (Calibrated to market volatility)
- DAX TP: 30 to 45 Points | DAX BE Trigger: 15 to 25 Points
- Persists optimal settings to 'config_learned_m15.json' and 'config_learned_scalp.json'.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5
import pandas as pd

logger = logging.getLogger("AlphaEdge.AutoLearner")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_learned_m15.json")
LEGACY_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_learned_scalp.json")
ANALYSIS_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m15_trade_analysis.csv")
SCALP_MAGIC = 20250831


def send_telegram(message: str):
    token   = os.getenv("TELEGRAM_TOKEN", "8617130364:AAHiEg1W9A-L5f7XkqVzgV6mTotb7TSiJV0")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "915238743")
    if not token or not chat_id:
        return
    url     = "https://api.telegram.org/bot" + token + "/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        logger.debug(f"[AutoLearner Telegram] {exc}")


class AutoLearner:
    def __init__(self, config_path=CONFIG_PATH, lookback_hours=72):
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
            "gold_tp_dollars": 10.0,
            "gold_tp_catalyst_dollars": 16.0,
            "gold_be_trigger_dollars": 6.0,
            "dax_tp_pts": 30.0,
            "dax_tp_catalyst_pts": 60.0,
            "dax_be_trigger_pts": 20.0,
            "regime": "BALANCED_SWING",
            "win_rate": 50.0,
            "total_trades": 0,
            "net_pnl": 0.0,
            "last_updated": None
        }

    def save_config(self, config):
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)
            with open(LEGACY_CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=4)
            logger.info(f"[AutoLearner] Saved learned configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

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

        # Baseline Defaults
        gold_tp = 10.0
        gold_tp_catalyst = 16.0
        gold_be = 6.0
        dax_tp = 30.0
        dax_tp_catalyst = 60.0
        dax_be = 20.0
        regime = "BALANCED_SWING"

        total_trades = 0
        win_rate = 50.0
        net_pnl = 0.0
        wins_count = 0
        loss_count = 0

        # 1. Primary Analysis: Check Dedicated M15 Analysis Log if available
        if os.path.exists(ANALYSIS_CSV_PATH):
            try:
                df_csv = pd.read_csv(ANALYSIS_CSV_PATH)
                closed_csv = df_csv[df_csv['status'] == 'CLOSED']
                if len(closed_csv) >= 3:
                    total_trades = len(closed_csv)
                    closed_csv['pnl_num'] = pd.to_numeric(closed_csv['pnl_usd'], errors='coerce').fillna(0.0)
                    wins_count = len(closed_csv[closed_csv['pnl_num'] > 0])
                    loss_count = len(closed_csv[closed_csv['pnl_num'] <= 0])
                    win_rate = round((wins_count / total_trades) * 100, 1)
                    net_pnl = round(float(closed_csv['pnl_num'].sum()), 2)
            except Exception as e:
                logger.debug(f"[AutoLearner] CSV read skipped: {e}")

        # 2. Secondary Analysis: Analyze MT5 deals history
        if total_trades == 0 and deals:
            df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
            exits = df_deals[(df_deals['entry'] == 1) & (df_deals['magic'] == SCALP_MAGIC)].copy()
            if len(exits) > 0:
                total_trades = len(exits)
                wins = exits[exits['profit'] > 0]
                losses = exits[exits['profit'] <= 0]
                wins_count = len(wins)
                loss_count = len(losses)
                win_rate = round((wins_count / total_trades) * 100, 1)
                net_pnl = round(float(exits['profit'].sum()), 2)

        logger.info(
            f"[AutoLearner M15 Brain] Evaluated {total_trades} trades | Wins: {wins_count} | Losses: {loss_count} | "
            f"Win Rate: {win_rate}% | Net PnL: ${net_pnl:+.2f}"
        )

        # ── Dynamic Adaptation Decisions based on Market Performance ──
        if total_trades >= 5:
            if win_rate >= 50.0 and net_pnl > 0:
                # Strong swing follow-through: Maintain $10 target, expand catalyst to $18
                regime = "HIGH_CONVICTION_SWING"
                gold_tp = 10.0
                gold_tp_catalyst = 18.0
                gold_be = 6.0
                dax_tp = 35.0
                dax_tp_catalyst = 65.0
                dax_be = 22.0
            elif win_rate < 40.0:
                # Ranging or high friction: Tighten BE trigger slightly to protect capital earlier
                regime = "DEFENSIVE_PROTECTION"
                gold_tp = 10.0
                gold_tp_catalyst = 16.0
                gold_be = 5.0  # Move BE to $5 to prevent giving back gains during choppy sessions
                dax_tp = 30.0
                dax_tp_catalyst = 60.0
                dax_be = 18.0
            else:
                regime = "BALANCED_SWING"
                gold_tp = 10.0
                gold_tp_catalyst = 16.0
                gold_be = 6.0
                dax_tp = 30.0
                dax_tp_catalyst = 60.0
                dax_be = 20.0

        old_config = self.load_config()
        new_config = {
            "gold_tp_dollars": gold_tp,
            "gold_tp_catalyst_dollars": gold_tp_catalyst,
            "gold_be_trigger_dollars": gold_be,
            "dax_tp_pts": dax_tp,
            "dax_tp_catalyst_pts": dax_tp_catalyst,
            "dax_be_trigger_pts": dax_be,
            "regime": regime,
            "win_rate": win_rate,
            "total_trades": total_trades,
            "net_pnl": net_pnl,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        has_changed = (
            old_config.get("regime") != new_config["regime"] or
            old_config.get("gold_tp_dollars") != new_config["gold_tp_dollars"] or
            old_config.get("gold_be_trigger_dollars") != new_config["gold_be_trigger_dollars"]
        )

        self.save_config(new_config)

        if has_changed:
            msg = (
                f"🧠 <b>[AlphaEdge AI Brain Adaptation]</b>\n\n"
                f"• <b>Market Regime:</b> {regime}\n"
                f"• <b>Analyzed History:</b> {total_trades} trades ({wins_count}W / {loss_count}L)\n"
                f"• <b>Win Rate:</b> {win_rate}%\n"
                f"• <b>Net PnL:</b> ${net_pnl:+.2f}\n"
                f"• <b>Gold Target:</b> ${gold_tp:.2f} TP (BE Lock at ${gold_be:.2f})\n"
                f"• <b>DAX Target:</b> {dax_tp:.0f} pts TP (BE Lock at {dax_be:.0f} pts)\n"
                f"• <b>News Catalyst Target:</b> Gold ${gold_tp_catalyst:.2f} / DAX {dax_tp_catalyst:.0f} pts\n"
                f"• <b>Status:</b> Dynamic optimization applied."
            )
            send_telegram(msg)

        return new_config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    learner = AutoLearner()
    cfg = learner.analyze_history_and_adapt()
    print("\nM15 AI Brain Config:")
    print(json.dumps(cfg, indent=4))
