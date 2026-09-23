"""
agent/validate_relationship_map.py
------------------------------------
Pre-flight validator for config/relationship_map.json.

Checks every key (except "_default") for common copy-paste mistakes and
implausible formats that would silently break the router at runtime.

Rules
-----
1. Flag keys containing "+", spaces, dashes, or any letters — these look
   like saved contact formats (e.g. "+91 98123-45670") not bare JID numbers.
2. Flag keys whose digit length is fewer than 8 or more than 15 — outside
   the realistic range for any international phone number.
3. Confirm "_default" exists and is one of the four known tier values;
   warn loudly if it's a typo or missing.
4. Exit with code 1 if any issues were found, 0 if everything is clean —
   safe to wire into a pipeline as a pre-flight gate.

Usage:
    python3 agent/validate_relationship_map.py
    python3 agent/validate_relationship_map.py --map config/relationship_map.json

Run from the project root.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
KNOWN_TIERS   = {"family", "friend", "professional", "unknown"}
MIN_DIGITS    = 8
MAX_DIGITS    = 15
BAD_CHARS_RE  = re.compile(r"[+\s\-a-zA-Z]")   # +, spaces, dashes, letters

# ── CLI arg ───────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate config/relationship_map.json before running the router."
    )
    parser.add_argument(
        "--map",
        default="config/relationship_map.json",
        help="Path to the relationship map JSON file (default: config/relationship_map.json)",
    )
    return parser.parse_args()


def main() -> None:
    args   = parse_args()
    issues: list[str] = []
    warnings: list[str] = []

    # ── Load the file ─────────────────────────────────────────────────────────
    map_path = Path(args.map)
    if not map_path.exists():
        print(f"❌  File not found: {map_path}")
        sys.exit(1)

    try:
        # utf-8-sig strips a BOM if present (common on Windows), falls back
        # gracefully on files without one — safe on all platforms.
        with map_path.open(encoding="utf-8-sig") as f:
            rel_map: dict[str, str] = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"❌  Invalid JSON in {map_path}: {exc}")
        sys.exit(1)

    print()
    print("══════════════════════════════════════════════")
    print(f"  Validating {map_path}")
    print("══════════════════════════════════════════════")
    print(f"  {len(rel_map)} total entries (including _default)\n")

    # ── Rule 3: check _default ────────────────────────────────────────────────
    if "_default" not in rel_map:
        issues.append('Missing "_default" key — router will hard-code "unknown" as fallback.')
    else:
        default_val = rel_map["_default"]
        if default_val not in KNOWN_TIERS:
            warnings.append(
                f'"_default" is set to "{default_val}" which is not one of '
                f'{sorted(KNOWN_TIERS)} — possible typo.'
            )
        else:
            print(f'  ✅  "_default": "{default_val}"  (recognised tier)')

    # ── Rules 1 & 2: check every non-default key ──────────────────────────────
    phone_keys = [k for k in rel_map if k != "_default"]

    for key in phone_keys:
        key_issues: list[str] = []

        # Rule 1 — bad characters
        bad = BAD_CHARS_RE.findall(key)
        if bad:
            unique_bad = sorted(set(bad))
            key_issues.append(
                f"contains disallowed character(s) {unique_bad} "
                f"— looks like a saved-contact format, not a bare JID number"
            )

        # Rule 2 — digit count (count only digit chars in case Rule 1 also fires)
        digit_count = sum(c.isdigit() for c in key)
        if digit_count < MIN_DIGITS:
            key_issues.append(
                f"only {digit_count} digit(s) — too short for a real phone number "
                f"(minimum {MIN_DIGITS})"
            )
        elif digit_count > MAX_DIGITS:
            key_issues.append(
                f"{digit_count} digits — too long for a real phone number "
                f"(maximum {MAX_DIGITS})"
            )

        if key_issues:
            for msg in key_issues:
                issues.append(f'  Key "{key}": {msg}')
        else:
            print(f'  ✅  "{key}": {rel_map[key]}  ({digit_count} digits — ok)')

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("══════════════════════════════════════════════")

    if warnings:
        print("  ⚠️   WARNINGS")
        print("══════════════════════════════════════════════")
        for w in warnings:
            print(f"  ⚠️   {w}")
        print()

    if issues:
        print("  ❌  ISSUES FOUND")
        print("══════════════════════════════════════════════")
        for iss in issues:
            print(f"  ❌  {iss}")
        print()
        print(f"  {len(issues)} issue(s) must be fixed before using this map in the router.")
        print(f"  Keys should be bare digits only, e.g.  \"919812345670\": \"friend\"")
        print()
        sys.exit(1)
    else:
        if warnings:
            print("  ✅  No hard errors — but review the warnings above.")
        else:
            print("  ✅  All keys are valid. Safe to use in the router.")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
