"""Secure Execution Gateway (SEG) package initializer.

Expose stable, backward-compatible public symbols used by integrators.
The `config` name is kept pointing to the moved `seg.core.config` module
to avoid breaking existing imports.
"""

from . import actions, core, middleware, routes
from .app import app  # expose ASGI app at package level
from .core import config

__all__ = ["app", "core", "config", "actions", "middleware", "routes"]
