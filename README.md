# AlphaEdge Institutional Multi-Timeframe (MTF) & Whale Flow Swing Engine

AlphaEdge is an institutional-grade algorithmic trading architecture engineered for **MetaTrader 5 (MT5)**. It synthesizes top-down multi-timeframe structural analysis, liquidity sweep detection, volume climax verification, and automated risk containment.

---

## 🏛️ Core Architectural Pillars

### 1. Fixed Daily Dealing Range (PDH / PDL Anchored)
To eliminate intraday **parallax errors** caused by rolling windows shifting during active sessions, AlphaEdge anchors dealing ranges directly to confirmed **Previous Day High (PDH)** and **Previous Day Low (PDL)**:
- **Equilibrium (50%)**: True midpoint of the previous day's confirmed range.
- **Discount Zone ($\le 35\%$)**: Institutional accumulation territory (BUY permitted, SELL strictly forbidden).
- **Premium Zone ($\ge 65\%$)**: Institutional distribution territory (SELL permitted, BUY strictly forbidden).
- *Fallback*: Automatically falls back to H4 50-bar rolling window during session opens or data gaps.

### 2. Precious Metals Mirror (`XAUUSDm` $\leftrightarrow$ `XAGUSDm`)
Gold and Silver share macroeconomic fundamentals (USD valuation, inflation expectations, risk sentiment). To prevent harmful hedge drag or conflicting signals:
- **Synchronized Execution**: Confirmation on Gold automatically triggers a mirrored entry on Silver (and vice versa) if the counterpart has no open position and is not in cooldown.
- **Direction Lock**: If one metal holds an active position (e.g. Gold BUY), any opposite setup on the sister metal (e.g. Silver SELL) is blocked immediately.

### 3. M5 Micro-Structure Pullback Confirmation
AlphaEdge never enters blindly at the peak of an impulse. When H4 macro bias and M15 momentum align:
- The engine monitors the M5 timeframe for micro-pullback exhaustion.
- Orders execute only when a completed M5 candle demonstrates a structural turn (bullish rejection breaking prior bar high for BUYs, bearish rejection breaking prior bar low for SELLs).

### 4. 2-Stage Dynamic Profit Protection
Every trade is actively shielded without manual intervention:
- **Stage 1 (Break-Even Shield)**: Shifts Stop Loss to Entry + buffer once target profit is attained to eliminate fakeout risk.
- **Stage 2 (Profit Lock Shield)**: Moves Stop Loss into solid guaranteed profit as the trade expands toward full Take Profit.

### 5. Overnight Spread-Buffer Gate (23:00 EAT)
Broker rollover windows (21:00–01:00 UTC / 00:00–04:00 EAT) frequently suffer from artificial spread spikes of \$1.50–\$3.50+ on precious metals.
- **At 23:00 EAT**:
  - Positions already locked at BE or profit lock run overnight untouched.
  - Healthy positions with original stops have their SL widened to a **$45 buffer from current price**, creating ample clearance so rollover spreads cannot trigger an accidental stop-out.
  - Positions carrying deep losses ($> -\$25$) are closed immediately to prevent widening risk on invalidated setups.

---

## 🎯 Active Assets Configuration

| Asset | Ticker | Lot Size | Full TP | Max Initial SL | Stage 1 BE | Stage 2 Profit Lock |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Gold** | `XAUUSDm` | `0.02` | **+$60.00** (30.0 pts) | **$36.00** (18.0 pts) | +$20.00 | +$35.00 $\rightarrow$ Lock +$25.00 |
| **Silver** | `XAGUSDm` | `0.02` | **+$60.00** ($0.60) | **$36.00** ($0.36) | +$20.00 | +$35.00 $\rightarrow$ Lock +$25.00 |
| **Dow Jones** | `US30m` | `0.25` | **+$60.00** (240.0 pts) | **$36.00** (144.0 pts) | +$20.00 | +$35.00 $\rightarrow$ Lock +$25.00 |
| **Crude Oil** | `USOILm` | `0.05` | **+$35.00** ($0.70) | **$25.00** ($0.50) | +$15.00 | +$25.00 $\rightarrow$ Lock +$20.00 |

### 🔭 Shadow Portfolio (Real-Time Paper Tracking)
AlphaEdge actively scans and records paper swing setups on 6 observation assets to evaluate historical consistency and prospective rotation:
- `EURUSDm` (Euro FX)
- `USTECm` (Nasdaq 100)
- `GBPUSDm` (British Pound)
- `US500m` (S&P 500)
- `GBPJPYm` (Guppy)
- `DE30m` (DAX 40)

---

## ⚡ News Catalyst Engine (`news_catalyst_engine.py`)

Integrates real-time macroeconomic event feeds (ForexFactory / FairEconomy) to safeguard against volatility shocks:
- **Pre-News Freeze (T-5m)**: Tightens profit protection and blocks new order fills.
- **Catalyst Impulse (T+0 to T+25m)**: Adapts profit targets during sustained post-release expansions.
- **Persistent Local Cache**: Local storage (`economic_calendar_cache.json`) prevents rate limiting.

---

## ⏰ Operational Windows & Cooldowns

- **Day Trading Window**: **08:00 to 20:00 EAT** (Monday to Friday).
- **Overnight Spread-Buffer Routine**: **23:00 to 23:10 EAT**.
- **Post-Closure Cooldown**: **60 minutes** per asset after every trade exit (enforced from both execution timestamp and closure timestamp) to prevent revenge trading or false re-entries.

---

## 🚀 Execution & Telegram Controls

### Launching the Bot
```powershell
python alphaedge.py
```

### Interactive Telegram Commands
- `/status` — Displays account balance, equity, active trades, and engine health.
- `/pnl` — Floating and realized PnL summary.
- `/shadow` — Complete performance breakdown across all shadow assets.
- `/start_scanner` / `/stop_scanner` — Interactive runtime controls.
