"""File-related action subpackage.

This package contains file-specific action handlers and their
corresponding Pydantic schemas. Keeping a small `__init__` makes the
subpackage discoverable by `pkgutil` and importlib during runtime
discovery.

Note: action modules themselves perform registration with the central
registry at import time (see `register_action(...)` calls in each
module). Avoid adding heavy side-effects here.
"""

from __future__ import annotations

# Expose public modules for clarity; actual registration occurs in the
# individual modules (e.g. checksum.py).
__all__ = ["checksum", "schemas"]
