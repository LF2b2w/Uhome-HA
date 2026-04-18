"""Pytest setup for standalone u_tec tests.

The resolver lives in `custom_components/u_tec/optimistic.py` and has
no Home Assistant imports. Adding that directory to `sys.path` lets tests
import it as a top-level module without triggering the package's
`__init__.py` (which pulls in Home Assistant).
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "custom_components" / "u_tec"))
