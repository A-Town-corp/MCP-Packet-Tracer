"""Compatibility shim for the upstream `twofish` package on modern Python.

The PyPI `twofish` wrapper (twofish.py) does `import imp` and calls
`imp.find_module('_twofish')[1]` purely to locate its compiled C extension.
The `imp` module was deprecated since 3.4 and **removed in Python 3.12**, so a
stock `import twofish` raises ``ModuleNotFoundError: No module named 'imp'`` on
3.12+ (this is the "patched twofish" problem on newer interpreters).

Importing this module *before* `twofish` installs a minimal ``imp`` (backed by
``importlib``) that provides just the ``find_module`` behaviour twofish needs,
so the cipher works unchanged on every Python version and OS. It is a no-op on
Python < 3.12, where the real ``imp`` is used.
"""
from __future__ import annotations

import sys

if "imp" not in sys.modules:
    try:  # Python < 3.12 still ships the real module.
        import imp  # noqa: F401
    except ModuleNotFoundError:
        import importlib.util
        import types

        def _find_module(name, path=None):
            spec = importlib.util.find_spec(name)
            if spec is None or spec.origin is None:
                raise ImportError(f"No module named {name!r}")
            # twofish.py only reads element [1] (the file path of _twofish).
            return (None, spec.origin, ("", "", 3))

        _shim = types.ModuleType("imp")
        _shim.find_module = _find_module
        sys.modules["imp"] = _shim
