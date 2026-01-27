"""Secure Execution Gateway (SEG) package initializer."""

__all__ = ["app", "config"]

from .app import app  # expose ASGI app at package level
