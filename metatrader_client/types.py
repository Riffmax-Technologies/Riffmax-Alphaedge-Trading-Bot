"""
Minimal types mapping for legacy imports in the project.
Defines `TradeRequestActions` and `OrderType` constants used by the codebase.
"""
import MetaTrader5 as mt5


class TradeRequestActions:
    DEAL = mt5.TRADE_ACTION_DEAL
    PENDING = mt5.TRADE_ACTION_PENDING
    SLTP = getattr(mt5, 'TRADE_ACTION_SLTP', mt5.TRADE_ACTION_DEAL)


class OrderType:
    BUY = mt5.ORDER_TYPE_BUY
    SELL = mt5.ORDER_TYPE_SELL
    BUY_LIMIT = getattr(mt5, 'ORDER_TYPE_BUY_LIMIT', mt5.ORDER_TYPE_BUY)
    SELL_LIMIT = getattr(mt5, 'ORDER_TYPE_SELL_LIMIT', mt5.ORDER_TYPE_SELL)
