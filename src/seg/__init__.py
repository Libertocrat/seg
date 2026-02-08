"""
Secure Execution Gateway (SEG) package.

This package exposes the application factory and shared components.
The ASGI application is intentionally NOT instantiated at import time
to avoid configuration side-effects.
"""

from . import actions, core, middleware, routes
from .core import config

__all__ = ["core", "config", "actions", "middleware", "routes"]
