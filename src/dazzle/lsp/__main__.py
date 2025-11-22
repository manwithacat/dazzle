"""
Entry point for DAZZLE LSP server.

Usage:
    python -m dazzle.lsp
"""

from .server import start_server

if __name__ == "__main__":
    start_server()
