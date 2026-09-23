# WhatsApp Persona Automation

A **RAG-based NLP pipeline** that learns your personal texting style from WhatsApp chat exports and generates contextually appropriate, persona-consistent auto-replies using LLMs.

## Architecture

```
[ Incoming Message ]
        ↓
[ Router: Phone # → Relationship Tier ]
        ↓
[ Decision Engine: Reply vs. Escalate to Human ]
        ↓
[ RAG Retrieval: ChromaDB similarity search ]
        ↓
[ Persona Injection: relationship-aware tone rules ]
        ↓
[ LLM Generation: Gemini ]
        ↓
[ Human-like Delay ]
        ↓
[ Send via Baileys WhatsApp Bridge ]
```

## Two-Brain Architecture

| Brain | Role |
|---|---|
| **Persona Brain** | Structured few-shot prompt — identity, Hinglish nuances, tone rules per relationship |
| **History Brain** | ChromaDB vector store of past message→reply pairs, segmented by relationship |

## Features

- 🗣️ **Style replication** — learns vocabulary, reply length, emoji usage, and code-switching (English/Hinglish/Bengali) from real chats
- 🔀 **Relationship routing** — distinct persona and memory per contact (gf, client, friends, group)
- 🛡️ **Safety engine** — auto-escalates sensitive topics (money, conflict, unknown senders) to human review
- ⏱️ **Human-like delays** — simulates realistic typing latency
- 🔒 **Privacy-first** — runs fully locally; no chat data leaves your machine

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12+ |
| LLM API | Google Gemini (free tier) |
| Vector DB | ChromaDB |
| Embeddings | sentence-transformers |
| WhatsApp Bridge | Baileys (Node.js) |
| Dashboard | Streamlit |

## Project Structure

```
├── agent/
│   ├── router.py             # Resolves JID → relationship tier
│   ├── decision_engine.py    # 3-layer reply/ignore pipeline
│   ├── generator.py          # Gemini reply generator with RAG + persona
│   └── batch_test.py         # End-to-end pipeline test
├── ingestion/
│   ├── parse_export.py       # Parse raw WhatsApp .txt exports → clean JSONL pairs
│   ├── retrieval.py          # ChromaDB RAG retrieval module
│   ├── embed_to_chroma.py    # Embed parsed pairs into ChromaDB
│   └── validate_pairs.py     # 5-point quality validation report
├── persona/
│   ├── persona.json          # Master persona config (identity, rules, style metrics)
│   ├── gf/style_signals.json
│   ├── client/style_signals.json
│   └── roshun/style_signals.json
├── config/
│   ├── relationship_map.json         # Phone number → tier mapping
│   ├── contact_relationship_map.json # Contact name → tier mapping
│   └── constants.py                  # Shared constants (ack words, etc.)
├── data/
│   └── raw_export/           # ⚠️ gitignored — place your WhatsApp .txt exports here
└── .env.example              # API key template
```

## Setup

```bash
# 1. Clone
git clone https://github.com/koustavdatascience/whatsapp-persona-automation.git
cd whatsapp-persona-automation

# 2. Install Python deps
pip install -r requirements.txt

# 3. Add your API key
cp .env.example .env
# edit .env and add your GEMINI_API_KEY

# 4. Place your WhatsApp exports
# Export chats from WhatsApp → put .txt files in data/raw_export/

# 5. Parse & embed
python ingestion/parse_export.py --name "You"
python ingestion/embed_to_chroma.py

# 6. Run the batch test
python -m agent.batch_test
```

## Data Privacy

Raw chat exports and processed JSONL files are **gitignored by default**.
Never commit real conversation data to a public repository.

---

Built by [@koustavdatascience](https://github.com/koustavdatascience)
