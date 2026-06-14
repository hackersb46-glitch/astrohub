"""
M9 ASCOM v1.0 - Alpaca Server

ASCOM Alpaca Protocol Server on port 5555.
Provides REST API compatible with ASCOM Alpaca standard for NINA and other clients.

Usage:
    python -m ascom.alpaca.server --host 0.0.0.0 --port 5555

Author: 雅痞张@南方天文
"""

from .server import create_alpaca_app, AlpacaServer
from .telescope import TelescopeAlpacaDriver

__all__ = ["create_alpaca_app", "AlpacaServer", "TelescopeAlpacaDriver"]
