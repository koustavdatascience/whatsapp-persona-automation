import argparse
from collections import Counter
import json
import os
import re
import sys

# Bengali/Hinglish-in-Latin-script target vocabulary
HINGLISH_WORDS = {
    "ha",
    "mane",
    "nah",
    "dhur",
    "bara",
    "acha",
    "babesh",
    "bhai",
    "haa",
    "toh",
}

# Emoji extraction regex pattern (Unicode character ranges)
EMOJI_PATTERN = re.compile(
    r'['
    r'\U0001F600-\U0001F64F'  # Emoticons
    r'\U0001F300-\U0001F5FF'  # Symbols & Pictographs
    r'\U0001F680-\U0001F6FF'  # Transport & Map Symbols
    r'\U0001F1E0-\U0001F1FF'  # Flags
    r'\U00002600-\U000027BF'  # Miscellaneous Symbols & Dingbats
    r'\U0001F900-\U0001F9FF'  # Supplemental Symbols and Pictographs
    r'\U0001FA70-\U0001FAFF'  # Symbols and Pictographs Extended-A
    r']'
)

# Regex matching WhatsApp export header variations
MESSAGE_HEADER_REGEX = re.compile(
    r'^(?:\[)?\d{1,4}[/.-]\d{1,4}[/.-]\d{1,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?(?:\])?\s*(?:-\s*)?(?P<sender>[^:]+):\s*(?P<message>.*)$',
    re.IGNORECASE,
)


def parse_whatsapp_chat(file_path: str, target_sender: str):
    """Reads a WhatsApp export file and extracts messages sent by target_sender."""
    messages = []
    current_sender = None
    current_message_lines = []

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            clean_line = line.rstrip('\r\n')
            match = MESSAGE_HEADER_REGEX.match(clean_line)
            if match:
                if current_sender and current_sender == target_sender:
                    messages.append('\n'.join(current_message_lines))

                current_sender = match.group('sender').strip()
                current_message_lines = [match.group('message')]
            else:
                if current_sender:
                    current_message_lines.append(clean_line)

        if current_sender and current_sender == target_sender:
            messages.append('\n'.join(current_message_lines))

    return messages


def analyze_style_signals(messages: list[str], target_name: str):
    """Computes style statistics from sender's messages."""
    total_messages = len(messages)
    if total_messages == 0:
        return None

    total_words = 0
    hinglish_count = 0
    all_emojis = []

    for msg in messages:
        words = msg.split()
        total_words += len(words)

        msg_words = set(re.findall(r'\b\w+\b', msg.lower()))
        if msg_words & HINGLISH_WORDS:
            hinglish_count += 1

        emojis = EMOJI_PATTERN.findall(msg)
        all_emojis.extend(emojis)

    avg_words = total_words / total_messages
    hinglish_ratio = (hinglish_count / total_messages) * 100
    top_emojis = Counter(all_emojis).most_common(15)

    return {
        "sender_name": target_name,
        "total_sample_size": total_messages,
        "avg_words_per_message": round(avg_words, 2),
        "hinglish_ratio_percent": round(hinglish_ratio, 2),
        "hinglish_ratio": f"{round(hinglish_ratio, 2)}%",
        "top_15_emojis": [
            {"emoji": emoji, "count": count} for emoji, count in top_emojis
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze texting style signals from a WhatsApp export."
    )
    parser.add_argument(
        "--file", required=True, help="Path to WhatsApp .txt export file"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Exact sender name as it appears in the export",
    )
    parser.add_argument(
        "--output",
        default="persona/style_signals.json",
        help="Output JSON path (default: persona/style_signals.json)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ Error: File not found at path '{args.file}'")
        sys.exit(1)

    print(
        f"🔍 Analyzing WhatsApp chat export '{args.file}' for sender"
        f" '{args.name}'..."
    )
    messages = parse_whatsapp_chat(args.file, args.name)

    if not messages:
        print("\n⚠️ WARNING: Found 0 matching messages for sender name:")
        print(f"   --> '{args.name}'")
        print(
            "   Please double-check the exact sender name in the raw export"
            " file."
        )
        print("   Example format in raw chat: '[DATE, TIME] Sender Name: ...'")
        sys.exit(0)

    stats = analyze_style_signals(messages, args.name)

    # Print human-readable summary
    print("\n" + "=" * 50)
    print("📊 TEXTING STYLE SIGNALS SUMMARY")
    print("=" * 50)
    print(f"👤 Sender Name           : {stats['sender_name']}")
    print(f"📩 Total Sample Size      : {stats['total_sample_size']} messages")
    print(f"📏 Avg Message Length    : {stats['avg_words_per_message']} words")
    print(
        f"🇧🇩 Hinglish/Bengali Ratio: {stats['hinglish_ratio_percent']}%"
        " (messages with target vocabulary)"
    )
    print("😀 Top 15 Emojis Used     :")
    if stats["top_15_emojis"]:
        for item in stats["top_15_emojis"]:
            print(f"   {item['emoji']} : {item['count']} times")
    else:
        print("   (No emojis detected)")
    print("=" * 50 + "\n")

    # Save output to specified output path
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"✅ Style signals successfully written to '{args.output}'")


if __name__ == "__main__":
    main()
