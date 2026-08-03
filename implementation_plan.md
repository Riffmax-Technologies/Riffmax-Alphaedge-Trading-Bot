# Implementation Plan for Enhancements

## Goal Description

- **Add M5 RSI Momentum Recovery filter** to sharpen entry precision by ensuring trades are only taken when RSI indicates an oversold/overbought condition with confirming momentum.
- **Update trading credentials** from the existing Exness $50 account to the newly opened Deriv account with a $10,000 balance.

## User Review Required

> [!IMPORTANT]
> The new Deriv credentials (account ID, API token, broker URL, etc.) are required to update `trade_config.py`. Please provide these details.
>
> The RSI filter thresholds (e.g., oversold <30, overbought >70) and any momentum confirmation logic (e.g., require RSI to improve for 2 consecutive 5‑minute candles before entering) need confirmation.

## Open Questions

- What are the exact **Deriv API credentials** (account ID, token, server URL) you want to use?
- Do you want to keep the existing Exness credentials as fallback or remove them entirely?
- Preferred **RSI parameters**: period length, oversold/overbought thresholds, and momentum window (e.g., require RSI to improve for 2 consecutive 5‑minute candles before entering).
- Should the RSI filter be applied **only on entry** or also on exit/trailing stop adjustments?

## Proposed Changes

---
### Trading Bot Core (`alphaedge.py`)

- Import the RSI function from `indicators.py` if not already imported.
- In the 5‑minute EMA crossover confirmation block, calculate the 5‑minute RSI.
- Add logic to check:
  - **Buy**: RSI < **oversold_threshold** (default 30) **and** RSI is increasing compared to the previous candle (momentum recovery).
  - **Sell**: RSI > **overbought_threshold** (default 70) **and** RSI is decreasing compared to the previous candle.
- Encapsulate this logic in a new helper function `rsi_momentum_filter(symbol, timeframe='M5')` returning a boolean for entry eligibility.
- Ensure the filter runs after the EMA crossover check and before placing a trade.

---
### Configuration (`trade_config.py`)

- Add a new section `DERIV_CONFIG` with fields:
  ```python
  DERIV_ENABLED = True
  DERIV_ACCOUNT_ID = "<your_account_id>"
  DERIV_API_TOKEN = "<your_api_token>"
  DERIV_BROKER_URL = "wss://api.deriv.com"  # example
  DERIV_BASE_BALANCE = 10000
  ```
- Optionally keep the existing `EXNESS_CONFIG` but disable it (`EXNESS_ENABLED = False`).
- Update any credential‑loading logic to select the active broker based on the enabled flag.

---
### Indicators (`indicators.py`)

- Verify the RSI implementation exists; if not, add a simple RSI calculation using typical price.
- Export `calculate_rsi(data, period=14)` for use by the core.

## Verification Plan

### Automated Tests
- Run existing unit tests (if any) to ensure no regressions.
- Add a quick sanity script to fetch recent 5‑minute candles for a symbol and confirm `rsi_momentum_filter` returns expected booleans given mocked RSI values.

### Manual Verification
- Deploy the bot in paper‑trading mode with the new Deriv credentials.
- Monitor Telegram alerts for entries; confirm they only fire when RSI conditions are met.
- Verify that trades are placed on the Deriv demo account and not on Exness.

---
*Please review the above plan and provide the missing credential details and any preferences for the RSI parameters.*
