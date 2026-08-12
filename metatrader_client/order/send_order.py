"""
Minimal `send_order` helper that wraps `mt5.order_send` to support the existing codebase.
It accepts a connection object (the `mt5` module) and returns a structured dict.
"""
from __future__ import annotations
import logging
import MetaTrader5 as mt5

logger = logging.getLogger("metatrader_client.order.send_order")


def _pick_filling_mode(request):
    candidates = []
    for attr in ("ORDER_FILLING_FOK", "ORDER_FILLING_IOC", "ORDER_FILLING_RETURN"):
        if hasattr(mt5, attr):
            candidates.append(getattr(mt5, attr))

    for filling_mode in candidates:
        probe_request = dict(request)
        probe_request["type_filling"] = filling_mode
        check = mt5.order_check(probe_request)
        if check and getattr(check, "retcode", None) in (0, mt5.TRADE_RETCODE_DONE):
            return filling_mode

    return candidates[0] if candidates else 0


def send_order(connection, *, action, order_type, symbol, volume, price=None, stop_loss=0.0, take_profit=0.0, comment: str = ""):
    try:
        # Build a basic request compatible with mt5.order_send
        req = {
            "action": action,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            # price may be None for market orders (TRADE_ACTION_DEAL)
            "price": float(price) if price is not None else 0.0,
            "sl": float(stop_loss) if stop_loss else 0.0,
            "tp": float(take_profit) if take_profit else 0.0,
            "deviation": 10,
            "comment": comment if isinstance(comment, str) else str(comment),
            "type_time": mt5.ORDER_TIME_GTC if hasattr(mt5, 'ORDER_TIME_GTC') else 0,
        }
        req["type_filling"] = _pick_filling_mode(req)

        res = mt5.order_send(req)
        if res is None:
            return {"success": False, "message": "mt5.order_send returned None"}
        if getattr(res, 'retcode', None) == mt5.TRADE_RETCODE_DONE or getattr(res, 'retcode', None) == 10009:
            # success
            return {"success": True, "data": res}
        else:
            msg = getattr(res, 'comment', str(getattr(res, 'retcode', 'unknown')))
            logger.error(f"Order failed: {msg}")
            return {"success": False, "message": msg}
    except Exception as e:
        logger.error(f"send_order exception: {e}")
        return {"success": False, "message": str(e)}
