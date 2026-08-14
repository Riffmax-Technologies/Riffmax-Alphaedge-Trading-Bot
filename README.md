# AlphaEdge Trading Bot 

AlphaEdge is a fully autonomous, institutional-grade MetaTrader 5 (MT5) trading bot built for high-frequency scanning and execution. Designed to trade across Forex, Crypto, Metals, and Indices, it utilizes a concurrent multi-strategy architecture to execute precision entries while strictly enforcing dynamic account risk management.

---

## ⚙️ Core Architecture

AlphaEdge runs continuously, scanning an active watchlist of assets (like `XAUUSDm`, `BTCUSDm`, `EURUSDm`) on every 5-minute candle close. It dispatches market data to a highly optimized Python risk engine that evaluates the market using three distinct, mathematically robust strategies.

The bot supports **Concurrent Multi-Asset Execution**, meaning it can hold multiple trades on the exact same asset simultaneously if different strategies trigger at the same time.

### 1. Core System (Institutional Daily Reversals)
The flagship strategy targets massive, highly manipulated institutional moves—specifically when market makers sweep the **Previous Day's High (PDH)** or **Previous Day's Low (PDL)** to hunt retail stop losses before reversing the daily trend.
- **Stop Loss:** A massive **3.0 ATR** buffer structurally placed completely outside the manipulation zone to survive the stop hunts.
- **Take Profit:** Deep structural targets aiming for 2:1 Reward-to-Risk or greater based on the daily reversal.

### 2. Liquidity Sweep (Intraday Mean Reversion)
A fast-acting mean-reversion strategy that hunts local, intraday liquidity sweeps. It enters aggressively when price pierces extreme structural lows/highs and is immediately rejected back into moving average alignment.
- **Stop Loss:** A wide **2.5 ATR** buffer beyond the local swing extreme to defend against market noise and wicks on volatile pairs like USOIL or Crypto.
- **Take Profit:** Targets the mean (Bollinger Band midline) or a trailing mathematical target.

### 3. Volatility Breakout (Momentum Expansion)
A trend-riding strategy that waits for periods of extreme compression and strikes when the price violently expands and closes completely outside the Bollinger Bands, riding the new momentum.
- **Stop Loss:** Dynamically trailed behind the midline of the volatility bands.

---

## 🛡️ Dynamic Risk Management Engine

AlphaEdge employs strict institutional risk modeling. Regardless of how wide the Stop Loss is mathematically placed (e.g., 3.0 ATR for the Core System vs tighter trailing stops for Breakouts), the bot's risk engine dynamically recalculates the exact **Lot Size** required to keep your maximum dollar loss to strictly **0.5% of your total account balance** per trade.

If a strategy requires a wider stop to survive volatility, the bot automatically reduces the lot size. You will never risk more than 0.5% on any single setup.

---

## 📱 Live Telegram Integration

The bot provides real-time, zero-latency alerts directly to your phone via Telegram. When a trade is fired, you receive an instant breakdown showing:
- The **Strategy Tag** (e.g., `AE_CORE`, `AE_SWEEP`, `AE_BREAK`)
- The Asset Symbol
- Action (BUY/SELL)
- Precise Entry, Stop Loss, and Take Profit prices
- Dynamically calculated Lot Size

---

## 🚀 How to Run the Bot

1. Ensure MetaTrader 5 is open, logged into your trading account, and Auto-Trading is enabled.
2. Ensure your `.env` file contains your MT5 credentials and Telegram Bot Token.
3. Open a terminal in the project directory and run the master boot script:

```bash
python start_bot.py
```

This single command safely initializes:
1. The **Autonomous Scanner** loop (checking the markets every 5 minutes).
2. The **Telegram Listener** (for manual status checks and reporting).

*(To stop the engine gracefully, simply press `Ctrl+C` in your terminal).*

---

## 📂 Project Structure

- `alphaedge.py`: The heart of the bot. Contains the 3 strategy formulas, the risk engine, MT5 execution logic, and concurrent trading architecture.
- `start_bot.py`: The master execution script that binds the scanner and the Telegram API together.
- `run_autonomous_scanner.py`: The isolated daemon that manages the scan cycles and data retrieval.
- `telegram_bot.py`: The listener script for handling incoming Telegram commands.
- `trade_log.csv`: A local ledger recording every trade executed by the bot.
