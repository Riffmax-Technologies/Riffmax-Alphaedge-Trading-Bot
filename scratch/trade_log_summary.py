import pandas as pd, json, sys
path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/trade_log.xlsx"
try:
    df = pd.read_excel(path, engine="openpyxl")
    total = len(df)
    wins = (df['profit'] > 0).sum()
    losses = (df['profit'] < 0).sum()
    win_rate = wins / total * 100 if total > 0 else 0
    total_pnl = df['profit'].sum()
    summary = {
        "total_trades": total,
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": win_rate,
        "total_pnl": total_pnl
    }
    print(json.dumps(summary))
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
