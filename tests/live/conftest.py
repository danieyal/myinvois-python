"""Load ``.env`` for the live tests, if one is present.

Live credentials are awkward to keep in the shell environment: they have to
survive across terminals and tool invocations, and exporting them persistently
writes a client secret into the shell profile or the Windows registry. A
gitignored ``.env`` in the repo root is the lesser evil, so this loads it.

Deliberately does **not** override variables already set in the environment --
an explicit ``MYINVOIS_LIVE_SUBMIT=1 uv run pytest ...`` must win over whatever
the file happens to contain, and a stale file should never silently redirect a
run at different credentials.

Scoped to ``tests/live/`` on purpose: the mocked suite must never depend on a
file that may or may not exist, or it stops being hermetic.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal ``KEY=VALUE`` loader -- enough for credentials, no more.

    Supports comments, blank lines, ``export`` prefixes and quoted values.
    Does not support multi-line values or variable interpolation; a credential
    file needing those is a sign something has gone wrong.
    """
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        # Real environment wins; see the module docstring.
        os.environ.setdefault(key, value)


_load_env_file(_ENV_FILE)
