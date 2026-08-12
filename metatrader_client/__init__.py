"""
Lightweight shim for metatrader_client used by the strategies.
Provides MT5Client wrapper around the MetaTrader5 package.
This is intentionally minimal: connect/disconnect and exposes `_connection`.
"""
from __future__ import annotations
import MetaTrader5 as mt5
import logging

logger = logging.getLogger("metatrader_client")


class MT5Client:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._connected = False
        # expose the underlying mt5 module as the connection object
        self._connection = mt5

    def connect(self) -> bool:
        try:
            login = int(self.config.get("login")) if self.config and self.config.get("login") else None
            password = self.config.get("password")
            server = self.config.get("server")
            if login and password and server:
                ok = mt5.initialize(login=login, password=password, server=server)
            else:
                ok = mt5.initialize()
            if not ok:
                logger.error(f"MT5 initialize failed: {mt5.last_error()}")
                raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"MT5Client.connect() error: {e}")
            raise

    def disconnect(self) -> None:
        try:
            if self._connected:
                mt5.shutdown()
                self._connected = False
        except Exception as e:
            logger.error(f"MT5Client.disconnect() error: {e}")
