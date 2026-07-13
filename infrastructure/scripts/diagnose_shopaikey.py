#!/usr/bin/env python3
"""Phase 0 ShopAIKey chat/embedding compatibility diagnostic.

Public entrypoint: `python infrastructure/scripts/diagnose_shopaikey.py`

Implementation lives in focused `shopaikey_diag` modules (settings/HTTP, chat,
tools/schema, streaming, embeddings). Never prints API keys, authorization
headers, or full secret configuration.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python infrastructure/scripts/diagnose_shopaikey.py` without install.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from shopaikey_diag.runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
