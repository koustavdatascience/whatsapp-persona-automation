# WhatsApp Language Model (WLM)

## 1. Project Overview & Goal
The objective of this project is to build an autonomous, privacy-focused, local WhatsApp auto-reply system — **WhatsApp Language Model (WLM)**. The system acts as a texting clone that auto-replies in the user's authentic voice, adapting tone, vocabulary, length, and emoji usage based on who is texting (family, friends, clients/colleagues, or group chats).

---

## 2. Core Problem Statement & Key Challenges
Traditional AI auto-responders sound robotic, overly formal, and generic. Fine-tuning an LLM on personal text messages is costly, goes stale quickly, lacks transparency, and fails to separate baseline identity from relationship-specific context.

To solve this, the system implements a **Two-Brain Architecture**:
- **Persona Brain (Identity & Rules)**: A structured few-shot prompt defining who the user is, their Hinglish nuances, texting habits, and relationship-based tone guidelines.
- **History Brain (Retrieval-Augmented Generation / RAG)**: A vector database (ChromaDB) holding past message-reply pairs split by relationship category.

### Critical System Requirements
1. **Safety & Decision Engine**: Automatically filter out messages that require human intervention (money transactions, urgent/serious matters, strangers, complex decisions).
2. **Relationship Routing**: Route messages to distinct memory collections (Family, Friends, Professional, Unknown/Group).
3. **Zero-Cost & Local**: Built entirely using free-tier tools (Gemini API, local ChromaDB, local Node.js/Baileys WhatsApp bridge).
4. **Human-like Dynamics**: Include natural response delays so responses do not feel instant or bot-like.

---

## 3. End-to-End Execution Pipeline (8 Stages)
```
[ Message In ] 
      ↓
[ Router (Phone # → Relationship Tier) ] 
      ↓
[ Decision Engine (Filter: Reply vs. Ignore/Human Escalation) ] 
      ↓
[ Retrieval (Search ChromaDB for top 2-3 similar past replies) ] 
      ↓
[ Persona Injection (Inject relationship tone & persona rules) ] 
      ↓
[ Generation (Gemini LLM response synthesis) ] 
      ↓
[ Human-like Delay (Simulate realistic typing latency) ] 
      ↓
[ Send (Baileys WhatsApp Bridge) ]
```

---

## 4. Current Repository Assets & Context

### 📄 Documentation & Curriculum
- **[`sept cohort plan.md`](file:///c:/Users/koust/OneDrive/Desktop/projects/whatsapp%20text%20automation/sept%20cohort%20plan.md)**: The 4-week step-by-step master plan covering architecture design, persona prompt engineering, ChromaDB vector indexing, decision engines, and Baileys bridge integration.

### 💬 Chat Datasets (`chats/` directory)
Exported raw WhatsApp chat logs available for processing into RAG history collections:
- **`chats/client chat.txt`**: Professional/freelance client conversations (work updates, project status, professional tone).
- **`chats/gf chat.txt`**: Personal/close relationship chat log (casual tone, internal references, high message frequency).
- **`chats/valorant group chat.txt`**: Casual gaming group chat log (slang, multi-participant dynamics).

---

## 5. Technology Stack
- **Core Languages**: Python 3.12+, Node.js 26+
- **LLM API**: Google Gemini API (Free Tier)
- **Vector DB / RAG**: ChromaDB
- **WhatsApp Gateway**: Baileys (Node.js WhatsApp Web API library)
- **UI & Dashboard**: Streamlit (Week 4 Cruise Control Console)
