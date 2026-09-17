"""
validate_pairs.py
-----------------
Reads data/processed_pairs.jsonl and runs a structured pass/fail report:
  1. Total pair count + per-conversation_id breakdown
  2. 5 random human-readable pair samples
  3. Leaked-noise scan (omitted / <Media / deleted / empty string)
  4. Suspiciously long my_reply (> 100 words)
  5. Near-identical / duplicate pairs
  6. Final one-line verdict

Standard library only: json, random, collections
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# ── config ──────────────────────────────────────────────────────────────────
JSONL_PATH   = Path("data/processed_pairs.jsonl")
NOISE_TOKENS = ["omitted", "<media", "deleted"]   # checked case-insensitively
MAX_WORDS    = 100
SAMPLE_SIZE  = 5
SEP          = "─" * 68

# ── ANSI helpers ─────────────────────────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def red(s):    return f"{RED}{s}{RESET}"
def yellow(s): return f"{YELLOW}{s}{RESET}"
def green(s):  return f"{GREEN}{s}{RESET}"
def bold(s):   return f"{BOLD}{s}{RESET}"


# ── helpers ───────────────────────────────────────────────────────────────────
def word_count(text: str) -> int:
    return len(text.split())


def near_identical(a: str, b: str) -> bool:
    """True if both strings are non-empty and identical after stripping/lowercasing."""
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and bool(b) and a == b


def has_noise(text: str) -> list:
    """Return list of noise tokens found in text (case-insensitive)."""
    lo = text.lower()
    return [tok for tok in NOISE_TOKENS if tok in lo]


def fmt_msg(text: str, indent: str = "     ") -> str:
    """Indent multi-line message for readable display."""
    lines = text.splitlines()
    return ("\n" + indent).join(lines)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if not JSONL_PATH.exists():
        print(red(f"❌  File not found: {JSONL_PATH}"))
        sys.exit(1)

    # ── load ──────────────────────────────────────────────────────────────────
    pairs = []
    with open(JSONL_PATH, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                obj["_lineno"] = lineno
                pairs.append(obj)
            except json.JSONDecodeError as exc:
                print(yellow(f"  ⚠  Line {lineno}: JSON parse error — {exc}"))

    issues = []

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECK 1 — total count + per-conversation breakdown
    # ═══════════════════════════════════════════════════════════════════════════
    conv_counts = defaultdict(int)
    for p in pairs:
        conv_counts[p.get("conversation_id", "unknown")] += 1

    print()
    print(bold("━━━  DATASET VALIDATION REPORT  ━━━"))
    print(f"File  : {JSONL_PATH}")
    print(f"Pairs : {bold(str(len(pairs)))}")
    print()
    print(bold("1 ▸  Per-Conversation Breakdown"))
    print(SEP)
    for cid, cnt in sorted(conv_counts.items()):
        if cnt == 0:
            print(red(f"  ❌  {cid:<30}  0 pairs  ← WARNING"))
            issues.append(f"Conversation '{cid}' has 0 pairs")
        else:
            print(f"  📄  {cid:<30}  {cnt} pairs")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECK 2 — 5 random human-readable samples
    # ═══════════════════════════════════════════════════════════════════════════
    print(bold("2 ▸  Random Pair Samples"))
    print(SEP)
    sample = random.sample(pairs, min(SAMPLE_SIZE, len(pairs)))
    for i, p in enumerate(sample, 1):
        cid = p.get("conversation_id", "?")
        ts  = p.get("timestamp", "")
        tm  = p.get("their_message", "").strip()
        mr  = p.get("my_reply", "").strip()
        print(f"\n  ── Sample {i}/{SAMPLE_SIZE}  [{cid}  •  {ts}]")
        print(f"  💬 THEM:\n     {fmt_msg(tm)}")
        print(f"  🤙 YOU :\n     {fmt_msg(mr)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECKS 3–5 — full scan
    # ═══════════════════════════════════════════════════════════════════════════
    noise_flags = []
    long_flags  = []
    dupe_flags  = []

    for p in pairs:
        ln  = p["_lineno"]
        cid = p.get("conversation_id", "unknown")
        tm  = p.get("their_message", "").strip()
        mr  = p.get("my_reply", "").strip()
        loc = f"line {ln} [{cid}]"

        # 3 — empty / leaked noise
        if not tm:
            noise_flags.append(f"{loc}: their_message is empty")
        else:
            for tok in has_noise(tm):
                noise_flags.append(f"{loc}: their_message contains '{tok}'")

        if not mr:
            noise_flags.append(f"{loc}: my_reply is empty")
        else:
            for tok in has_noise(mr):
                noise_flags.append(f"{loc}: my_reply contains '{tok}'")

        # 4 — suspiciously long reply
        wc = word_count(mr)
        if wc > MAX_WORDS:
            long_flags.append(f"{loc}: my_reply is {wc} words (>{MAX_WORDS})")

        # 5 — near-identical
        if near_identical(tm, mr):
            dupe_flags.append(f"{loc}: their_message ≈ my_reply  →  \"{tm[:60]}\"")

    # ── print check 3 ─────────────────────────────────────────────────────────
    print(bold("3 ▸  Leaked Noise / Empty Strings"))
    print(SEP)
    if noise_flags:
        print(yellow(f"  ⚠  {len(noise_flags)} issue(s) found:"))
        for f in noise_flags[:20]:
            print(f"     • {f}")
        if len(noise_flags) > 20:
            print(f"     … and {len(noise_flags) - 20} more")
        issues.extend(noise_flags)
    else:
        print(green("  ✅  No leaked noise or empty strings found."))
    print()

    # ── print check 4 ─────────────────────────────────────────────────────────
    print(bold("4 ▸  Suspiciously Long Replies  (> 100 words)"))
    print(SEP)
    if long_flags:
        print(yellow(f"  ⚠  {len(long_flags)} issue(s) found:"))
        for f in long_flags[:20]:
            print(f"     • {f}")
        if len(long_flags) > 20:
            print(f"     … and {len(long_flags) - 20} more")
        issues.extend(long_flags)
    else:
        print(green("  ✅  No suspiciously long replies."))
    print()

    # ── print check 5 ─────────────────────────────────────────────────────────
    print(bold("5 ▸  Near-Identical / Duplicate Pairs"))
    print(SEP)
    if dupe_flags:
        print(yellow(f"  ⚠  {len(dupe_flags)} issue(s) found:"))
        for f in dupe_flags[:20]:
            print(f"     • {f}")
        if len(dupe_flags) > 20:
            print(f"     … and {len(dupe_flags) - 20} more")
        issues.extend(dupe_flags)
    else:
        print(green("  ✅  No duplicate pairs detected."))
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # FINAL VERDICT
    # ═══════════════════════════════════════════════════════════════════════════
    print(SEP)
    if not issues:
        print(green(bold("✅  Looks good")))
    else:
        print(yellow(bold(f"⚠️   {len(issues)} issues found — review above")))
    print(SEP)
    print()


if __name__ == "__main__":
    main()
