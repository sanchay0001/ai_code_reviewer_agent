# 🔍 AI Code Review Agent

An autonomous AI agent that clones any public GitHub repository, parses Python source files using Abstract Syntax Trees, and generates structured review comments with severity ratings and confidence scores — all displayed in an interactive Streamlit dashboard.

> Built for the CipherSchools Advanced AI/ML Assignment | Domain: Agentic AI | Difficulty: Advanced

---

## 🚀 Live Demo

**[Coming soon — deploying to Streamlit Cloud]**

---

## 🏗️ How It Works

The agent runs as a 4-phase pipeline:

```
GitHub URL
    │
    ▼
Phase 1 — Ingestion (core/ingestion.py)
    GitPython shallow clone → validate URL → collect .py files
    Skips: venv, __pycache__, binary files, files > 200KB
    │
    ▼
Phase 2 — AST Parser (core/parser.py)
    Python ast module → extract functions, classes, module-level code
    Large classes split method-by-method for focused review
    Each chunk gets its file's imports attached as context
    │
    ▼
Phase 3 — LLM Reviewer (core/reviewer.py)
    Groq API with 3-key round-robin rotation
    Structured prompt → JSON comments with severity + confidence score
    Exponential backoff + retry on rate limits or failures
    │
    ▼
Phase 4 — Dashboard (app.py)
    Streamlit UI → live progress bar → filtered results
    Confidence bars, severity badges, "Verify This" labels
    Download as Markdown report or raw JSON
```

---

## ✨ Features

**Confidence Scoring**
Every comment has a self-rated confidence score from 0 to 100%. Comments below 50% are flagged with a "⚠️ Verify This" warning and shown in a separate section at the top of results — so you always know which findings need manual verification before acting on them.

| Score | Tier | Display |
|-------|------|---------|
| 75 – 100% | High | Normal comment |
| 50 – 74% | Medium | Caution indicator |
| 0 – 49% | Low | ⚠️ Verify This |

**3-Key Groq Rotation**
Rotates across 3 API keys round-robin. When one key hits a rate limit it immediately switches to the next — tripling the effective free-tier allowance without waiting.

**AST-Aware Chunking**
Splits files at function and class boundaries using Python's built-in `ast` module — not raw line counts. The LLM always sees complete, meaningful units of code.

**Resilient Pipeline**
Files with syntax errors are sent to the LLM as-is (the error itself is worth reporting). Binary files, encoding errors, and oversized files are skipped gracefully. The pipeline never crashes on a single bad file.

**Live Dashboard Filters**
Filter results by severity (critical / high / medium / low / info), confidence tier, and category (bug / security / performance / style / maintainability / error_handling / documentation).

---

## 📁 Project Structure

```
ai_code_reviewer_agent/
│
├── app.py                          # Streamlit dashboard
├── requirements.txt
├── .env.example                    # API key template
├── .gitignore
├── README.md
│
├── core/
│   ├── ingestion.py                # Phase 1 — clone + file collection
│   ├── parser.py                   # Phase 2 — AST chunking
│   └── reviewer.py                 # Phase 3 — Groq LLM review
│
├── tests/
│   ├── test_phase1_ingestion.py    #  8 tests
│   ├── test_phase2_parser.py       # 10 tests
│   ├── test_phase3.py              # 14 tests
│   └── test_phase4.py              # 23 tests
│
└── .streamlit/
    ├── config.toml                 # Theme and server settings
    └── secrets.toml.example        # Template for Streamlit Cloud
```

---

## ⚙️ Setup

### 1. Clone and enter the project
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

Edit `.env`:
```env
GROQ_API_KEY_1=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
GROQ_API_KEY_2=gsk_yyyyyyyyyyyyyyyyyyyyyyyy
GROQ_API_KEY_3=gsk_zzzzzzzzzzzzzzzzzzzzzzzz
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Get free Groq keys at [console.groq.com](https://console.groq.com)

### 5. Run
```bash
streamlit run app.py
```

Open **http://localhost:8501**, paste a public GitHub URL, and click **Review**.

---

## 🧪 Tests

```bash
python tests/test_phase1_ingestion.py   #  8 tests — ingestion
python tests/test_phase2_parser.py      # 10 tests — AST parser
python tests/test_phase3.py             # 14 tests — LLM reviewer
python tests/test_phase4.py             # 23 tests — dashboard + integration
```

All 55 tests pass with 0 failures.

---

## 🧠 Model & Prompt

| Setting | Value |
|---------|-------|
| Primary model | `llama-3.3-70b-versatile` |
| Fallback model | `llama-3.1-8b-instant` |
| Provider | Groq (free tier) |
| Temperature | 0.1 — low for consistent JSON output |
| Max tokens | 1200 per chunk |

The system prompt enforces JSON-only output with an explicit schema. `"Return [] if no issues"` prevents the model from hallucinating complaints on clean code. The confidence guide (90–100 = certain bug, 0–24 = speculative) anchors the 0–100 scale.

---

## ⚠️ Known Limitations

- **Python only** — JS/Go support would need `tree-sitter`
- **Public repos only** — private repos need a token injected into the clone URL
- **Large repos (500+ chunks)** — Groq free tier may throttle; adding longer delays between calls would help
- **No cross-file analysis** — each chunk is reviewed independently; bugs that span multiple files won't be caught

---

## 🔮 What I'd Build Next

- JavaScript / TypeScript support via `tree-sitter`
- GitHub PR integration — post inline review comments directly to pull requests
- Git diff mode — only review files changed since the last commit
- CI/CD integration — fail the pipeline if any critical issues are found
- Cross-file context — pass import graphs to the LLM for deeper analysis

---

## 📚 Repos Used for Testing

- [psf/requests](https://github.com/psf/requests) — integration tests and live demo
- [pallets/flask](https://github.com/pallets/flask) — URL validation tests

---

## 📄 License

MIT