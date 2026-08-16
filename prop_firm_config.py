import MetaTrader5 as mt5
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("PropFirmEngine")

class PropFirmEngine:
    def __init__(self, starting_balance: float, current_phase: int = 1):
        self.starting_balance = starting_balance
        self.current_phase = current_phase
        
        # Rules defined by User
        self.daily_loss_pct = 0.03 # 3%
        self.max_loss_pct = 0.06   # 6%
        self.profit_target_pct = 0.10 if current_phase == 1 else 0.0 # 10% for Phase 1
        
        # Maximum allowed risk per trade (Funded phase rule: "Max Risk-3% At any time")
        # Challenge phase defaults to global bot risk (e.g. 0.5%), but we cap it to 3% globally for safety.
        self.max_risk_per_trade_pct = 0.03 
        
    def get_start_of_day_balance(self) -> float:
        """Calculate start-of-day balance by taking current balance and subtracting today's closed PnL."""
        acc = mt5.account_info()
        if not acc:
            return self.starting_balance
            
        current_balance = acc.balance
        
        now = datetime.now()
        start_of_day = datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(start_of_day, now)
        
        todays_pnl = 0.0
        if deals:
            for deal in deals:
                # Add profit, commission, and swap
                todays_pnl += (deal.profit + deal.commission + deal.swap)
                
        # If current balance is $10,100 and today's PnL is +$100, start of day was $10,000
        start_of_day_balance = current_balance - todays_pnl
        return start_of_day_balance

    def check_trade_safety(self, potential_loss_usd: float) -> tuple[bool, str]:
        """
        Validates if taking a trade with a specific potential loss (Stop Loss risk) 
        will violate the Prop Firm rules.
        """
        acc = mt5.account_info()
        if not acc:
            return False, "Cannot connect to MT5 to verify equity."
            
        current_equity = acc.equity
        start_of_day_balance = self.get_start_of_day_balance()
        
        # 1. Check Max Static Loss (6% of Starting Balance)
        absolute_loss_limit = self.starting_balance * (1.0 - self.max_loss_pct)
        if (current_equity - potential_loss_usd) <= absolute_loss_limit:
            msg = f"Trade Blocked: Risking ${potential_loss_usd:.2f} would drop equity to ${(current_equity - potential_loss_usd):.2f}, breaching the Static Max Loss limit of ${absolute_loss_limit:.2f} (6% of {self.starting_balance})."
            logger.warning(msg)
            return False, msg
            
        # 2. Check Daily Loss Limit (3% of Start-of-Day Balance)
        daily_loss_limit = start_of_day_balance * (1.0 - self.daily_loss_pct)
        if (current_equity - potential_loss_usd) <= daily_loss_limit:
            msg = f"Trade Blocked: Risking ${potential_loss_usd:.2f} would drop equity to ${(current_equity - potential_loss_usd):.2f}, breaching the Daily Loss limit of ${daily_loss_limit:.2f} (3% of SOD {start_of_day_balance:.2f})."
            logger.warning(msg)
            return False, msg
            
        # 3. Check Max Risk Per Trade (3%)
        if potential_loss_usd > (self.starting_balance * self.max_risk_per_trade_pct):
            msg = f"Trade Blocked: Risking ${potential_loss_usd:.2f} exceeds the 3% Max Risk rule."
            logger.warning(msg)
            return False, msg
            
        # 4. Check if Profit Target is hit (Phase 1 Only)
        if self.current_phase == 1:
            profit_target_amount = self.starting_balance * (1.0 + self.profit_target_pct)
            if current_equity >= profit_target_amount:
                msg = f"Target Reached! Equity is ${current_equity:.2f} (Target: ${profit_target_amount:.2f}). Trading paused to secure Phase 1."
                logger.info(msg)
                return False, msg
                
        return True, "Safe to execute."
        
    def get_status_report(self) -> str:
        """Returns a string formatted for Telegram with the current Challenge status."""
        acc = mt5.account_info()
        if not acc:
            return "Prop Firm Engine: Disconnected."
            
        sod = self.get_start_of_day_balance()
        daily_loss_limit = sod * (1.0 - self.daily_loss_pct)
        max_loss_limit = self.starting_balance * (1.0 - self.max_loss_pct)
        target = self.starting_balance * (1.0 + self.profit_target_pct) if self.current_phase == 1 else "Funded Phase (No Target)"
        
        msg = f"🏆 <b>Prop Firm Engine Status (Phase {self.current_phase})</b>\n"
        msg += f"Equity: ${acc.equity:.2f}\n"
        msg += f"Start of Day: ${sod:.2f}\n\n"
        msg += f"🚨 <b>Limits:</b>\n"
        msg += f"Daily Floor (3%): ${daily_loss_limit:.2f}\n"
        msg += f"Max Floor (6%): ${max_loss_limit:.2f}\n"
        if self.current_phase == 1:
            msg += f"🎯 <b>Target (10%):</b> ${target:.2f}\n"
            
        return msg
