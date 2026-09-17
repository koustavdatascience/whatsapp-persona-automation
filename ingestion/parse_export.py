import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys

# Supported WhatsApp export header pattern:
# Handles bracketed format: [8/26/26, 10:35:35 AM] Sender: Msg
# Handles unbracketed format: 8/26/26, 10:35 AM - Sender: Msg
LINE_PATTERN = re.compile(
    r'^(?:\[)?(?P<date>\d{1,4}[/.-]\d{1,4}[/.-]\d{1,4}),?\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)(?:\])?\s*(?:-\s*)?(?P<sender>[^:]+):\s*(?P<message>.*)$'
)

# System, media, and call markers to exclude
NOISE_MARKERS = [
    "messages and calls are end-to-end encrypted",
    "<media omitted>",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "gif omitted",
    "document omitted",
    "voice message omitted",   # <voice message omitted>
    "contact card omitted",
    "location: ",
    "this message was deleted",
    "you deleted this message",
    "missed voice call",
    "missed video call",
    "voice call",
    "video call",
    "[call]",
    "call ended",
    "created group",
    "changed the subject",
    "added you",
    "changed this group's icon",
    "you were added",
    "security code changed",
]

# Catches any WhatsApp <X omitted> bracketed pattern not in the list above
_OMITTED_RE = re.compile(r'<[^>]+ omitted>', re.IGNORECASE)

ONE_WORD_ACKS = {
    "ok",
    "okay",
    "k",
    "kk",
    "haan",
    "hmm",
    "thanks",
    "thank you",
    "cool",
    "nice",
}


def derive_conversation_id(file_path: Path) -> str:
    """Derives a slugified conversation_id from the filename."""
    name = file_path.stem
    prefix = "WhatsApp Chat with "
    if name.startswith(prefix):
        name = name[len(prefix) :]
    slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    return slug or "conversation"


def is_noise(text: str) -> bool:
    """Returns True if the text is a system/media message, call log, or standalone acknowledgement."""
    lower = text.lower().strip()
    if any(marker in lower for marker in NOISE_MARKERS):
        return True
    # Catch any remaining <X omitted> bracket pattern (e.g. <voice message omitted>)
    if _OMITTED_RE.search(lower):
        return True
    clean = re.sub(r"[^\w\s]", "", lower)
    if clean in ONE_WORD_ACKS:
        return True
    return False


def parse_file(path: Path, my_name: str) -> list[dict]:
    """Returns raw (sender, message, timestamp) tuples, continuation-merged while skipping noise lines."""
    entries = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            match = LINE_PATTERN.match(line)
            if match:
                date, time, sender, message = (
                    match.group("date"),
                    match.group("time"),
                    match.group("sender"),
                    match.group("message"),
                )
                if not is_noise(message):
                    entries.append({
                        "sender": sender.strip(),
                        "message": message,
                        "timestamp": f"{date} {time}",
                    })
            elif entries:
                # Continuation line — skip if it contains a call log or system marker
                if is_noise(line):
                    continue
                entries[-1]["message"] += "\n" + line
    return entries


def group_into_turns(entries: list[dict]) -> list[dict]:
    """Merge consecutive messages from the same sender into one turn, cleaning embedded noise lines."""
    turns = []
    for entry in entries:
        clean_lines = [
            line for line in entry["message"].split("\n") if not is_noise(line)
        ]
        if not clean_lines:
            continue
        clean_message = "\n".join(clean_lines)

        if turns and turns[-1]["sender"] == entry["sender"]:
            turns[-1]["message"] += "\n" + clean_message
        else:
            turns.append({
                "sender": entry["sender"],
                "timestamp": entry["timestamp"],
                "message": clean_message,
            })
    return turns


def _near_identical(a: str, b: str) -> bool:
    """True when both sides are non-empty and identical after normalisation."""
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and bool(b) and a == b


# Timestamp formats WhatsApp uses across locales
_TS_FORMATS = [
    "%m/%d/%y %I:%M:%S %p",
    "%m/%d/%Y %I:%M:%S %p",
    "%d/%m/%y %I:%M:%S %p",
    "%d/%m/%Y %I:%M:%S %p",
    "%m/%d/%y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%y %H:%M",
    "%m/%d/%y %I:%M %p",
]

def _parse_ts(ts_str: str):
    """Try parsing a timestamp string with known WhatsApp formats. Returns datetime or None."""
    ts_str = ts_str.strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def build_pairs(
    turns: list[dict], my_name: str, conversation_id: str,
    cap: int = 500, max_gap_hours: int = 24
) -> list[dict]:
    """Extracts (their_message -> my_reply) turn pairs capped at last N pairs.
    Drops pairs where the reply came more than max_gap_hours after the message.
    """
    pairs = []
    for i in range(1, len(turns)):
        if turns[i]["sender"] == my_name and turns[i - 1]["sender"] != my_name:
            their_msg = turns[i - 1]["message"].strip()
            my_reply  = turns[i]["message"].strip()

            # Drop pairs where both sides are empty or near-identical
            if not their_msg or not my_reply:
                continue
            if _near_identical(their_msg, my_reply):
                continue

            # Drop stale pairs — reply came too many hours later
            t_their = _parse_ts(turns[i - 1]["timestamp"])
            t_reply  = _parse_ts(turns[i]["timestamp"])
            if t_their and t_reply:
                if (t_reply - t_their) > timedelta(hours=max_gap_hours):
                    continue

            pairs.append({
                "conversation_id": conversation_id,
                "their_message": their_msg,
                "my_reply": my_reply,
                "timestamp": turns[i]["timestamp"],
            })
    return pairs[-cap:]


def main():
    parser = argparse.ArgumentParser(
        description="Parse WhatsApp exports into processed Q&A turn pairs."
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Exact sender name as it appears in the export (e.g. 'You')",
    )
    parser.add_argument(
        "--input_dir",
        default="data/raw_export",
        help="Path to directory containing raw export .txt files",
    )
    parser.add_argument(
        "--output",
        default="data/processed_pairs.jsonl",
        help="Path to output master .jsonl file",
    )

    args = parser.parse_args()

    my_name = args.name.rstrip(":").strip()

    input_path = Path(args.input_dir)
    if not input_path.exists() or not list(input_path.glob("*.txt")):
        fallback = Path("chats")
        if fallback.exists() and list(fallback.glob("*.txt")):
            input_path = fallback

    txt_files = list(input_path.glob("*.txt"))
    if not txt_files:
        print(f"❌ Error: No .txt files found in '{input_path}'")
        sys.exit(1)

    print(
        f"📂 Processing {len(txt_files)} conversation export(s) from"
        f" '{input_path}' for sender '{my_name}'..."
    )
    print("=" * 60)

    all_pairs = []
    summary = []

    per_chat_dir = Path("data/processed_chats")
    per_chat_dir.mkdir(parents=True, exist_ok=True)

    for file_path in txt_files:
        conv_id = derive_conversation_id(file_path)
        entries = parse_file(file_path, my_name)
        turns = group_into_turns(entries)
        pairs = build_pairs(turns, my_name, conv_id, cap=500)

        all_pairs.extend(pairs)
        summary.append((file_path.name, conv_id, len(pairs)))

        # Write per-chat .jsonl file
        chat_jsonl_path = per_chat_dir / f"{conv_id}.jsonl"
        with open(chat_jsonl_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # Write master combined .jsonl file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print("\n📊 PER-CONVERSATION PARSING SUMMARY")
    print("=" * 60)
    for filename, conv_id, count in summary:
        warning_str = (
            f" ⚠️  WARNING: 0 pairs extracted (sender '{my_name}' not found in raw chat)"
            if count == 0
            else ""
        )
        print(
            f"📄 {filename:<25} | ID: {conv_id:<20} | Pairs Kept:"
            f" {count}{warning_str}"
        )

    print("=" * 60)
    print(f"✅ Master combined pairs written to: '{output_path}'")
    print(f"📁 Individual per-chat .jsonl files written to: '{per_chat_dir}/'")


if __name__ == "__main__":
    main()
