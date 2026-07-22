"""Verify the built sdist and wheel before they are published.

Run from the repo root after `uv build`:

    uv run --no-project python scripts/check_dist.py

Two classes of mistake are checked, both of which are unrecoverable once a
release is on PyPI (a version number can never be reused):

1. **Missing runtime data.** `py.typed` and `codes/_data/*.json` are not
   importable Python modules, so they only ship because of the explicit
   `[tool.uv.build-backend] data-includes` entry. If that entry regresses, the
   package still builds and imports, but `myinvois.codes` raises at runtime on
   a wheel install and type-checkers silently ignore the package.

2. **Leaked signing material.** `tests/fixtures/cert/` holds a dummy private
   key and certificate that are deliberately force-tracked in git so the
   byte-parity tests can pin against fixtures signed with them. They are
   harmless (self-signed, test-only) but shipping a file named
   `*_key.pem` inside a published distribution is the kind of thing that
   triggers secret scanners and erodes trust, so it is a hard failure here.

Exits non-zero with a description of every problem found.
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

DIST = Path(__file__).resolve().parents[1] / "dist"

# Files that must be present in the wheel, relative to the package root.
REQUIRED_WHEEL_MEMBERS = (
    "myinvois/py.typed",
    "myinvois/codes/_data/classification.json",
    "myinvois/codes/_data/countries.json",
    "myinvois/codes/_data/currencies.json",
    "myinvois/codes/_data/msic.json",
    "myinvois/codes/_data/payment_means.json",
    "myinvois/codes/_data/states.json",
    "myinvois/codes/_data/taxes.json",
    "myinvois/codes/_data/units.json",
)

# Anything matching these must NOT appear in either distribution. Keyed on the
# path so a source module such as `ubl/signing/_cert.py` (legitimate) is not
# confused with an actual PEM payload.
FORBIDDEN_PATTERNS = (
    re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(^|/)tests?/", re.IGNORECASE),
    re.compile(r"(^|/)fixtures?/", re.IGNORECASE),
)


def _wheel_and_sdist() -> tuple[Path, Path]:
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        sys.exit(
            f"expected exactly one wheel and one sdist in {DIST}, "
            f"found {len(wheels)} wheel(s) and {len(sdists)} sdist(s). "
            "Remove stale builds and re-run `uv build`."
        )
    return wheels[0], sdists[0]


def _wheel_members(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def _sdist_members(sdist: Path) -> list[str]:
    with tarfile.open(sdist) as tf:
        # Strip the leading `myinvois-<version>/` directory so the paths line
        # up with how they are written in the repo.
        return [name.partition("/")[2] for name in tf.getnames()]


def main() -> int:
    if not DIST.is_dir():
        sys.exit(f"{DIST} does not exist -- run `uv build` first.")

    wheel, sdist = _wheel_and_sdist()
    wheel_members = _wheel_members(wheel)
    sdist_members = _sdist_members(sdist)

    problems: list[str] = []

    missing = [m for m in REQUIRED_WHEEL_MEMBERS if m not in wheel_members]
    for member in missing:
        problems.append(
            f"{wheel.name}: missing required member {member!r} -- check the "
            "`[tool.uv.build-backend] data-includes` entry in pyproject.toml"
        )

    for label, members in ((wheel.name, wheel_members), (sdist.name, sdist_members)):
        for member in members:
            if not member or member.endswith("/"):
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(member):
                    problems.append(
                        f"{label}: must not ship {member!r} (matched {pattern.pattern})"
                    )
                    break

    if problems:
        print(f"Distribution check FAILED ({len(problems)} problem(s)):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    scanned = len(wheel_members) + len(sdist_members)
    print(f"Distribution check passed: {wheel.name}, {sdist.name}")
    print(f"  {len(REQUIRED_WHEEL_MEMBERS)} required members present")
    print(f"  no test fixtures or key material in {scanned} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
