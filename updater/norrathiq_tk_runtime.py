"""PyInstaller runtime hook for machines whose Python Tcl data is incomplete."""
from __future__ import annotations

import os
import sys

root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
os.environ["TCL_LIBRARY"] = os.path.join(root, "_tcl_data")
os.environ["TK_LIBRARY"] = os.path.join(root, "_tk_data")
