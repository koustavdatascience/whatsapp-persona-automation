"""
config/constants.py
--------------------
Shared constants used across the WLM pipeline.

Import from here rather than redefining in individual scripts so any
future change (e.g. adding "sure" to ONE_WORD_ACKS) only needs to happen
in one place.
"""

# Standalone one-word acknowledgements that carry no conversational content.
# Used by ingestion/parse_export.py to filter noise from chat exports.
ONE_WORD_ACKS: set[str] = {
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
