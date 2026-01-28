"""Core helpers and shared infrastructure for the SEG application.

This package exposes cross-cutting components used by the application,
for example exception handlers, metrics helpers and global logging
configuration.

Exports:
    http_exception_handler, generic_exception_handler
"""

from .config import Settings, settings
from .exceptions import generic_exception_handler, http_exception_handler

__all__ = [
    "Settings",
    "settings",
    "generic_exception_handler",
    "http_exception_handler",
]
