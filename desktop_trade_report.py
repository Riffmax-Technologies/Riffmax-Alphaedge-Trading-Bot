from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import pandas as pd
import MetaTrader5 as mt5


PROJECT_ROOT = Path(__file__).resolve().parent
DESKTOP_DIR = Path(r"C:\Users\DATA ENG. OLA\Desktop")
REPORT_XLSX = DESKTOP_DIR / "AlphaEdge_Trade_Report.xlsx"
REPORT_CSV = DESKTOP_DIR / "AlphaEdge_Trade_Report.csv"


@dataclass
class TradeStats:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    avg_trade: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0


def _deal_row(deal) -> dict:
    data = deal._asdict()
    pnl = float(data.get("profit", 0.0)) + float(data.get("commission", 0.0)) + float(data.get("swap", 0.0))
    return {
        "time": datetime.fromtimestamp(data["time"]).isoformat(sep=" "),
        "position_id": data.get("position_id"),
        "ticket": data.get("ticket"),
        "symbol": data.get("symbol"),
        "type": data.get("type"),
        "entry": data.get("entry"),
        "volume": data.get("volume"),
        "price": data.get("price"),
        "sl": data.get("sl", 0.0),
        "tp": data.get("tp", 0.0),
        "profit": data.get("profit", 0.0),
        "commission": data.get("commission", 0.0),
        "swap": data.get("swap", 0.0),
        "net_pnl": pnl,
        "comment": data.get("comment", ""),
    }


def _build_trade_table(days_back: int = 30) -> pd.DataFrame:
    now = datetime.now()
    start = now - timedelta(days=days_back)
    deals = mt5.history_deals_get(start, now) or []
    rows = [_deal_row(deal) for deal in deals if deal is not None]
    if not rows:
        return pd.DataFrame(columns=[
            "position_id", "symbol", "entry_time", "exit_time", "side", "volume",
            "entry_price", "exit_price", "profit", "commission", "swap", "net_pnl", "comment"
        ])

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    entries = df[df["entry"].isin([0, 2])].copy()
    exits = df[df["entry"].isin([1, 3])].copy()

    trade_rows = []
    grouped_exits = exits.groupby("position_id")
    grouped_entries = entries.groupby("position_id")

    for position_id, exit_group in grouped_exits:
        entry_group = grouped_entries.get_group(position_id) if position_id in grouped_entries.groups else pd.DataFrame()
        entry_row = entry_group.iloc[0] if not entry_group.empty else None
        exit_row = exit_group.iloc[-1]
        trade_rows.append({
            "position_id": position_id,
            "symbol": exit_row["symbol"],
            "entry_time": entry_row["time"] if entry_row is not None else "",
            "exit_time": exit_row["time"],
            "side": "BUY" if str(exit_row["type"]) in ("0", "1") else "SELL",
            "volume": exit_row["volume"],
            "entry_price": entry_row["price"] if entry_row is not None else None,
            "exit_price": exit_row["price"],
            "profit": float(exit_group["profit"].sum()),
            "commission": float(exit_group["commission"].sum()),
            "swap": float(exit_group["swap"].sum()),
            "net_pnl": float(exit_group["net_pnl"].sum()),
            "comment": exit_row["comment"],
        })

    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades.sort_values(["exit_time", "position_id"], inplace=True)
    return trades


def _stats(df: pd.DataFrame) -> TradeStats:
    if df.empty:
        return TradeStats()

    net = df["net_pnl"] if "net_pnl" in df else df["profit"]
    wins = int((net > 0).sum())
    losses = int((net < 0).sum())
    breakeven = int((net == 0).sum())
    gross_profit = float(net[net > 0].sum())
    gross_loss = float(net[net < 0].sum())
    net_pnl = float(net.sum())
    total = int(len(df))
    return TradeStats(
        total_trades=total,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        avg_trade=float(net.mean()) if total else 0.0,
        profit_factor=(gross_profit / abs(gross_loss)) if gross_loss else 0.0,
        win_rate=(wins / total) * 100 if total else 0.0,
        max_win=float(net.max()) if total else 0.0,
        max_loss=float(net.min()) if total else 0.0,
    )


def refresh_report(days_back: int = 30) -> Path:
    trades = _build_trade_table(days_back=days_back)
    summary = _stats(trades)

    summary_rows = [
        ["Report generated", datetime.now().isoformat(sep=" ")],
        ["Lookback days", days_back],
        ["Total trades", summary.total_trades],
        ["Wins", summary.wins],
        ["Losses", summary.losses],
        ["Breakeven", summary.breakeven],
        ["Win rate (%)", round(summary.win_rate, 2)],
        ["Net PnL", round(summary.net_pnl, 2)],
        ["Gross profit", round(summary.gross_profit, 2)],
        ["Gross loss", round(summary.gross_loss, 2)],
        ["Profit factor", round(summary.profit_factor, 2)],
        ["Average trade", round(summary.avg_trade, 2)],
        ["Best trade", round(summary.max_win, 2)],
        ["Worst trade", round(summary.max_loss, 2)],
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["Metric", "Value"])

    with pd.ExcelWriter(REPORT_XLSX, engine="openpyxl") as writer:
        trades.to_excel(writer, sheet_name="Trades", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
    trades.to_csv(REPORT_CSV, index=False, encoding="utf-8")
    return REPORT_XLSX


def main() -> int:
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return 1
    try:
        path = refresh_report(days_back=30)
        print(f"Report saved to: {path}")
        print(f"CSV saved to: {REPORT_CSV}")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
