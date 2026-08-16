"""Load .env before anything reads os.environ.

Python does not read .env files on its own, so `backend/faers_prr.py` and
`backend/triage_summary.py` -- both of which call `os.environ.get(...)` at
import or call time -- would see nothing without this. Done here rather than
with python-dotenv to avoid a dependency for twelve lines, and because it runs
for `api.main` and `api.store` alike.

Real environment variables always win: on Render the key is set in the
dashboard and there is no .env file at all.
"""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

if _ENV_FILE.is_file():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _value = _line.partition("=")
        _key = _key.strip()
        _value = _value.strip().strip('"').strip("'")
        # Only fill gaps: a value already in the environment is authoritative.
        if _key and _value and not os.environ.get(_key):
            os.environ[_key] = _value
