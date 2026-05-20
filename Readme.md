<div align="center">

# 🔍 AI Code Review Agent

**An autonomous AI agent that clones any GitHub repository, parses code using Abstract Syntax Trees, and delivers confidence-rated review comments — all in a live Streamlit dashboard.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

[🚀 Live Demo](#) &nbsp;|&nbsp; [📸 Screenshots](#-screenshots) &nbsp;|&nbsp; [⚙️ Setup](#️-setup-instructions) &nbsp;|&nbsp; [🧪 Tests](#-running-tests)

</div>

---

## 📌 Overview

This project is a fully autonomous **AI-powered code review agent** built from scratch. Paste any public GitHub repository URL — the agent clones it, walks the file tree, extracts every function and class using AST parsing, sends each chunk to a Groq LLM for review, and renders the results in an interactive dashboard with severity badges, confidence scores, and a downloadable report.

> Built for the **CipherSchools Advanced AI/ML Assignment** (3-day deadline, Advanced difficulty)

---

## 📸 Screenshots

| Dashboard | Results with Confidence Scores |
|-----------|-------------------------------|
| ![Dashboard](https://github.com/sanchay0001/ai_code_reviewer_agent/raw/main/assets/dashboard.png) | ![Results](https://github.com/sanchay0001/ai_code_reviewer_agent/raw/main/assets/results.png) |

---

## 🏗️ Architecture

```
  GitHub URL Input
        │
        ▼
┌───────────────────────────────────────────────────┐
│  PHASE 1 — Ingestion          core/ingestion.py   │
│                                                   │
│  • GitPython shallow clone (depth=1, faster)      │
│  • Validates HTTPS GitHub URL with regex          │
│  • Walks file tree, filters .py files             │
│  • Skips: venv / __pycache__ / binary / empty     │
└────────────────────┬──────────────────────────────┘
                     │  [{path, content}, ...]
                     ▼
┌───────────────────────────────────────────────────┐
│  PHASE 2 — AST Parser           core/parser.py    │
│                                                   │
│  • Python built-in ast module (zero dependencies) │
│  • Extracts: functions, classes, module-level     │
│  • Large classes split method-by-method           │
│  • Attaches imports as context to every chunk     │
│  • Handles SyntaxError files gracefully           │
└────────────────────┬──────────────────────────────┘
                     │  [{chunk_id, code, type, ...}, ...]
                     ▼
┌───────────────────────────────────────────────────┐
│  PHASE 3 — LLM Reviewer       core/reviewer.py    │
│                                                   │
│  • Groq API with 3-key round-robin rotation       │
│  • LLaMA 3.3 70B (primary) / 3.1 8B (fallback)   │
│  • Prompt forces strict JSON schema output        │
│  • Confidence score 0–100% per comment            │
│  • Exponential backoff + retry on failures        │
└────────────────────┬──────────────────────────────┘
                     │  [{comments, severity, confidence}, ...]
                     ▼
┌───────────────────────────────────────────────────┐
│  PHASE 4 — Dashboard                     app.py   │
│                                                   │
│  • Streamlit UI with live progress bar            │
│  • Filter by severity / confidence / category     │
│  • "⚠️ Verify This" label for low confidence      │
│  • Download: Markdown report + Raw JSON           │
│  • Sidebar: severity bars, confidence stats       │
└───────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🎯 Confidence Scoring — Epistemic Humility
Every comment includes a **self-rated confidence score (0–100%)** with three tiers:

| Tier | Score | Display |
|------|-------|---------|
| 🟢 **High** | 75 – 100% | Normal comment card |
| 🟡 **Medium** | 50 – 74% | Caution indicator on progress bar |
| 🔴 **Low** | 0 – 49% | **⚠️ "Verify This"** warning — shown separately at the top |

Low-confidence comments are grouped into a dedicated section so reviewers know exactly which findings need manual verification before acting on them.

### 🔑 3-Key Groq Rotation — Triple the Rate Limit
The agent rotates across 3 Groq API keys in round-robin. When one key hits the rate limit it instantly rotates to the next — effectively tripling the free-tier allowance with zero wait time.

### 🌳 AST-Aware Chunking — Not Just String Splitting
Uses Python's built-in `ast` module to split files at **function and class boundaries** — not arbitrary line counts. Large classes are reviewed method-by-method. Every chunk includes the file's import list as context so the LLM understands dependencies.

### 🛡️ Production-Grade Resilience
- Files with syntax errors don't crash the pipeline — they're sent as-is (the error itself is worth reviewing)
- Binary / non-UTF-8 / oversized files are skipped gracefully
- `None` responses from the LLM are filtered before reaching the UI
- All 3 keys exhausted → graceful failure message per chunk, rest of review continues

### 🎛️ Live Filters
Filter results instantly by **Severity** (critical / high / medium / low / info), **Confidence Tier**, and **Category** (bug / security / performance / style / maintainability / error_handling / documentation).

---

## 📁 Project Structure

```
ai_code_reviewer_agent/
│
├── app.py                          # Streamlit dashboard — Phase 4
├── requirements.txt                # All pip dependencies
├── .env.example                    # API key template (safe to commit)
├── .gitignore                      # Excludes .env, venv, __pycache__
├── README.md
│
├── core/
│   ├── ingestion.py                # Phase 1 — Clone + file collection
│   ├── parser.py                   # Phase 2 — AST chunking
│   └── reviewer.py                 # Phase 3 — Groq LLM review
│
├── tests/
│   ├── test_phase1_ingestion.py    #  8 tests — URL validation, file collection
│   ├── test_phase2_parser.py       # 10 tests — AST extraction, edge cases
│   ├── test_phase3.py              # 14 tests — LLM calls, key rotation
│   └── test_phase4.py              # 23 tests — filters, report, integration
│
└── .streamlit/
    ├── config.toml                 # Theme + server settings
    └── secrets.toml.example        # Template for Streamlit Cloud secrets
```

---

## ⚙️ Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/sanchay0001/ai_code_reviewer_agent.git
cd ai_code_reviewer_agent
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API keys
```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Open `.env` and fill in your keys:
```env
GROQ_API_KEY_1=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
GROQ_API_KEY_2=gsk_yyyyyyyyyyyyyyyyyyyyyyyy
GROQ_API_KEY_3=gsk_zzzzzzzzzzzzzzzzzzzzzzzz
GITHUB_TOKEN=ghp_xxxxxxxxxxxx   # optional
```

Get free Groq keys at → [console.groq.com](https://console.groq.com)

### 5. Run the app
```bash
streamlit run app.py
```

Open **http://localhost:8501**, paste any public GitHub repo URL, and click **Review**.

---

## 🧪 Running Tests

```bash
# Phase 1 — Ingestion (8 tests)
python tests/test_phase1_ingestion.py

# Phase 2 — AST Parser (10 tests)
python tests/test_phase2_parser.py

# Phase 3 — LLM Reviewer (14 tests, makes Groq API calls)
python tests/test_phase3.py

# Phase 4 — Dashboard + Integration (23 tests)
python tests/test_phase4.py
```

**Total: 55 tests — 0 failures**

---

## 🧠 LLM & Prompt Design

| Setting | Value |
|---------|-------|
| Primary model | `llama-3.3-70b-versatile` |
| Fallback model | `llama-3.1-8b-instant` |
| Temperature | `0.1` (low = consistent JSON) |
| Max tokens | `1200` per chunk |
| Provider | [Groq](https://groq.com) — free tier |

The system prompt enforces **strict JSON-only output** with an explicit schema. Key decisions:
- `"Return [] if no issues"` prevents the model from hallucinating complaints on clean code
- Confidence guide (90–100 = certain, 0–24 = speculative) anchors the scoring scale
- File path + imports included in every prompt for full context

---

## ⚠️ Known Limitations

1. **Python only** — JS/Go support would need `tree-sitter`
2. **Public repos only** — private repos need a token in the clone URL
3. **Large repos (500+ chunks)** — Groq free tier may throttle; add longer delays between calls
4. **No cross-file analysis** — each chunk is reviewed independently

---

## 🔮 What I'd Build Next

- **JavaScript / TypeScript support** via `tree-sitter`
- **GitHub PR integration** — post inline review comments directly to pull requests
- **Git diff mode** — only review files changed since the last commit
- **CI/CD integration** — fail pipeline if any `critical` issues are found
- **Cross-file context** — pass import graphs to the LLM for better analysis

---

## 📚 Repos Used for Testing

| Repo | Purpose |
|------|---------|
| [psf/requests](https://github.com/psf/requests) | Integration tests, live demo |
| [pallets/flask](https://github.com/pallets/flask) | URL validation tests |

---

## 📄 License

MIT License — free to use and modify.

---

<div align="center">

Built with ❤️ using **Python · Groq · GitPython · Streamlit**

</div>