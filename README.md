# AlphaEdge Trading Bot

AlphaEdge is a live MT5 trading bot that scans for liquidity-sweep and pullback setups, then places trades with stop loss and take profit when the signal is confirmed.

## What It Runs

- `alphaedge.py` contains the main strategy logic.
- `run_autonomous_scanner.py` runs the scan loop every 2 minutes.
- `telegram_bot.py` provides manual commands and status checks.
- `start_bot.py` starts the scanner and Telegram bot together from one command.

## One-Command Start

From the project folder, run:

```powershell
python start_bot.py
```

This starts:

- the autonomous scanner
- the Telegram bot

## Strategy Summary

AlphaEdge currently looks for:

- liquidity sweep reversal setups
- Bollinger Band extreme pullbacks
- RSI momentum confirmation
- EMA 8 / EMA 21 direction alignment
- higher-timeframe confirmation on H1

When the bot approves a setup, it sends a live MT5 order with:

- broker-aware fill mode selection
- stop loss
- take profit
- trailing/breakeven management for open positions

## Files To Use

- `start_bot.py` for the full engine
- `run_autonomous_scanner.py` for scanner-only runs
- `telegram_bot.py` for manual Telegram control
- `alphaedge.py` for strategy and execution logic

## Notes

- The bot uses credentials from `.env`.
- Keep MT5 open and logged in before starting the engine.
- If you want no pending-order behavior and only immediate market entries, I can remove the pending branch next.
