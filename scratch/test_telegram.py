# test_telegram.py
import sys
import os

# Add paths to sys.path
scratch_dir = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch"
if scratch_dir not in sys.path:
    sys.path.insert(0, scratch_dir)

from alphaedge import send_telegram_alert
from trading_bot_skills.trade_config import TELEGRAM_ENABLED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def main():
    print("=== Testing Telegram Notification Alerts ===")
    print(f"TELEGRAM_ENABLED: {TELEGRAM_ENABLED}")
    print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
    print(f"TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
    
    if not TELEGRAM_ENABLED or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("\n[!] Please edit C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/.agents/trading_bot_skills/trade_config.py to enable Telegram and insert your actual token and chat ID, then run this test again.")
        return
        
    print("\nSending test message...")
    send_telegram_alert("🔔 <b>[AlphaEdge Test Alert]</b>\nThis is a successful test alert from your autonomous trading bot!")
    print("Sent. Please check your Telegram app.")

if __name__ == "__main__":
    main()
