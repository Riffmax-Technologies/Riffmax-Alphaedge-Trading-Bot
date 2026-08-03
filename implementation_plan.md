# Integrate Telegram Bot Alerts

This plan details how to add optional Telegram notification alerts to the bot. Whenever a trade is entered, modified (trailing stop/profit secure), or closed, the bot will send an alert directly to your Telegram chat.

## Open Questions
* **Credentials:** You will need to create a Telegram bot via `@BotFather` and retrieve your `Chat ID` (using `@userinfobot`). We will place placeholders for these in `trade_config.py` so you can fill them in easily.

---

## Proposed Changes

### 1. Configuration Setup

#### [MODIFY] [trade_config.py](file:///C:/Users/DATA%20ENG.%20OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/.agents/trading_bot_skills/trade_config.py)
* Add configuration parameters for Telegram bot alerts:
  ```python
  # Telegram Alert Settings
  TELEGRAM_ENABLED = False  # Set to True once you enter your token and chat ID
  TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
  TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
  ```

### 2. Notification Helper and Event Alerts

#### [MODIFY] [alphaedge.py](file:///C:/Users/DATA%20ENG.%20OLA/.gemini/antigravity/scratch/alphaedge.py)
* Import `TELEGRAM_ENABLED`, `TELEGRAM_TOKEN`, and `TELEGRAM_CHAT_ID` from `trade_config`.
* Implement a helper function `send_telegram_alert(message)` using python's built-in `urllib.request` (no extra external libraries needed).
* Trigger Telegram notifications on key events:
  * **Order Execution:** Send details of Symbol, Action, Lot Size, Entry, SL, and TP.
  * **Trailing Stop Adjustments:** Notify when a position's SL is moved to secure profits (0.5x ATR).
  * **Errors/Drawdown Limits:** Notify if a daily drawdown threshold is breached.

---

## Verification Plan

### Automated Tests
1. Run a test script to trigger a dummy Telegram alert using your configured token and chat ID to verify connection.
2. Verify that manual run of `alphaedge.py` compiles and imports without errors.

### Manual Verification
* Turn `TELEGRAM_ENABLED = True` inside `trade_config.py`, input your bot token and chat ID, and run the test script. Verify that a message arrives in your Telegram chat.
