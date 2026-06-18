from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
TMP_DIR = PROJECT_ROOT / ".tmp"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMP", str(TMP_DIR))
os.environ.setdefault("TEMP", str(TMP_DIR))
os.environ.setdefault("TMPDIR", str(TMP_DIR))
tempfile.tempdir = str(TMP_DIR)
