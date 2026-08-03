# trading_bot_skills/token_stub.py

"""Utility module to retrieve the optional TRADINGAGENTS_TOKEN.

The TradingAgents A‑Share analysis skill (which can enrich the bot with
fundamental data) requires an API token provided via the environment
variable ``TRADINGAGENTS_TOKEN``.  The core prop‑firm trading logic does not
depend on this token, so the bot can run without it.  This stub provides a
convenient accessor that raises an informative error only when the token
is actually requested.
"""

import os

def get_tradingagents_token() -> str:
    """Return the ``TRADINGAGENTS_TOKEN`` environment variable.

    Returns
    -------
    str
        The token string.

    Raises
    ------
    EnvironmentError
        If the environment variable is not set.  Callers should catch this
        exception and either disable the optional feature or prompt the
        user for the token.
    """
    token = os.getenv("TRADINGAGENTS_TOKEN")
    if not token:
        raise EnvironmentError(
            "TRADINGAGENTS_TOKEN is not set. The optional TradingAgents A‑Share "
            "analysis features are unavailable. Set the environment variable "
            "or disable the feature."
        )
    return token
