"""Extract MyInvois code tables from the PHP SDK into JSON fixtures.

Run from the repo root: `uv run python scripts/extract_codes.py`.
It reads `/tmp/phpsdk/src/Ubl/Constant/*.php` and writes JSON files to
`src/myinvois/codes/_data/`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict


class _TableSpec(TypedDict):
    out: str
    columns: list[tuple[str, str]]


PHPSDK = Path("/tmp/phpsdk/src/Ubl/Constant")
OUT = Path(__file__).resolve().parents[1] / "src" / "myinvois" / "codes" / "_data"
OUT.mkdir(parents=True, exist_ok=True)

# Map: PHP class => {output_filename, columns[(php_const, json_key)]}
#: Per-table extraction spec. A TypedDict so ``spec["out"]`` types as ``str``
#: and ``spec["columns"]`` as the column list, rather than unifying to a union
#: that neither ``Path / spec["out"]`` nor the column loop can use.
TABLES: dict[str, _TableSpec] = {
    "StateCodes": {
        "out": "states.json",
        "columns": [("CODE", "code"), ("STATE", "name")],
    },
    "TaxTypeCodes": {
        "out": "taxes.json",
        "columns": [("CODE", "code"), ("DESCRIPTION", "description")],
    },
    "PaymentMethodCodes": {
        "out": "payment_means.json",
        "columns": [("CODE", "code"), ("PAYMENT_METHOD", "name")],
    },
    "ClassificationCodes": {
        "out": "classification.json",
        "columns": [("CODE", "code"), ("DESCRIPTION", "description")],
    },
    "CountryCodes": {
        "out": "countries.json",
        "columns": [("CODE", "code"), ("COUNTRY", "name")],
    },
    "CurrencyCodes": {
        "out": "currencies.json",
        "columns": [("CODE", "code"), ("CURRENCY", "name")],
    },
    "MSICCodes": {
        "out": "msic.json",
        "columns": [
            ("CODE", "code"),
            ("DESCRIPTION", "description"),
            ("CATEGORY_REF", "category_ref"),
        ],
    },
    "UnitCodes": {
        "out": "units.json",
        "columns": [("CODE", "code"), ("NAME", "name"), ("DESCRIPTION", "description")],
    },
}


CONST_RE = re.compile(r"\bconst\s+(?P<name>[A-Z_0-9]+)\s*=\s*['\"](?P<val>[^'\"\\]*)['\"]")


def php_consts(php: str) -> dict[str, str]:
    """Top-level `const NAME = 'value'` definitions in the class body."""
    return {m.group("name"): m.group("val") for m in CONST_RE.finditer(php)}


def class_kv(cls: str, body: str, consts: dict[str, str]) -> dict[str, str]:
    """Parse `Class::CONST => value` pairs from one row, resolving refs."""
    pattern = re.compile(
        r"\b" + re.escape(cls) + r"::(?P<const>[A-Z_0-9]+)\s*=>\s*"
        r"(?:['\"](?P<str>[^'\"\\]*)['\"]|" + re.escape(cls) + r"::(?P<refconst>[A-Z_0-9]+))"
    )
    out: dict[str, str] = {}
    for m in pattern.finditer(body):
        if m.group("str") is not None:
            out[m.group("const")] = m.group("str")
        else:
            # Resolve e.g. CurrencyCodes::CODE => CurrencyCodes::MYR
            ref = m.group("refconst")
            if ref in consts:
                out[m.group("const")] = consts[ref]
    return out


def extract(cls: str) -> list[dict[str, str]]:
    php = (PHPSDK / f"{cls}.php").read_text(encoding="utf-8")
    consts = php_consts(php)
    ret = php.index("return")
    # Outer opening bracket of the returned array.
    open_b = php.index("[", ret)
    body = php[open_b + 1 :]
    # Find the matching closing `];` for the outer array and peel it.
    depth = 1
    end = len(body)
    for i, ch in enumerate(body):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = body[:end]

    # Now scan inner rows, deduping by `code` (UnitCodes has dups).
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    depth = 0
    cur_start = -1
    for i, ch in enumerate(body):
        if ch == "[":
            if depth == 0:
                cur_start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and cur_start >= 0:
                row_body = body[cur_start : i + 1]
                kv = class_kv(cls, row_body, consts)
                if kv and kv.get("CODE", "") not in seen:
                    seen.add(kv.get("CODE", ""))
                    rows.append(kv)
                cur_start = -1
    return rows


def main() -> None:
    for cls, spec in TABLES.items():
        rows = extract(cls)
        out_json = [
            {json_key: row.get(php_const, "") for php_const, json_key in spec["columns"]}
            for row in rows
            if row
        ]
        target = OUT / spec["out"]
        target.write_text(
            json.dumps(out_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        n = len(out_json)
        rel = target.relative_to(OUT.parent.parent.parent)
        print(f"{cls:24s}: {n:5d} rows -> {rel}")


if __name__ == "__main__":
    main()
