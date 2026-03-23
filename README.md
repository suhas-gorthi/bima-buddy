# 🛡️ Bima Buddy — AI Insurance Concierge

> *From zero to covered, and covered when it matters.*

Bima Buddy is an AI-powered insurance concierge built with **Streamlit** and **Claude (Anthropic)**. It replaces static insurance forms and confusing jargon with a warm, conversational experience — helping users find the right insurance plan, fill applications correctly, and fight rejected claims.

---

## ✨ Features

| Feature | Description |
|---|---|
| 💬 **Smart Profiling** | No forms. Bima Buddy learns your age, family, income, health history, and risk appetite through natural conversation. A live profile card updates in real time as you chat. |
| 💡 **Plan Recommendations** | 2–3 personalised insurance plans ranked by a weighted scoring model (sum insured adequacy, affordability, network hospitals, claim settlement ratio, and more). Includes side-by-side comparison and rider suggestions. |
| 🛒 **Guided Application** | Pre-filled application forms with 🔴🟡🟢 flags on critical questions. Red flags warn about the exact answers that cause claim rejections — especially pre-existing condition declarations. |
| 💳 **Simulated Payment Flow** | Full end-to-end payment experience: order summary with GST breakdown, UPI / Debit-Credit Card / Net Banking, a processing animation, and a downloadable policy confirmation. |
| ⚔️ **Rejection Fighter** | Paste or upload a claim rejection letter (PDF, image, or text). Bima Buddy identifies the rejection type, cites the applicable IRDAI regulation, calculates a win probability, and generates a ready-to-send appeal letter — in under 30 seconds. |
| 📎 **File Upload** | Upload rejection letters, policy documents, or any insurance file (PDF, TXT, PNG, JPG). Rejection letters are auto-detected and routed to the Rejection Fighter. |

---

## 🏗️ Architecture

Bima Buddy uses a **multi-agent backend** where each agent has a specialised system prompt and a distinct responsibility. The Streamlit frontend manages session state and routes between agents based on the conversation phase.

```
User Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                          │
│   Intent Classification · Phase Management · Routing    │
└───────┬──────────┬──────────┬──────────┬────────────────┘
        │          │          │          │
        ▼          ▼          ▼          ▼
  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────┐
  │ Profile  │ │Recommend-│ │Pre-fill │ │  Rejection   │
  │ Builder  │ │  ation   │ │  & Flag │ │   Fighter    │
  │  Agent   │ │  Agent   │ │  Agent  │ │    Agent     │
  └──────────┘ └──────────┘ └─────────┘ └──────────────┘
        │          │              │             │
        └──────────┴──────────────┴─────────────┘
                         │
                  Streamlit UI
         (Chat · Profile Card · Plan Cards ·
          Application Form · Payment Page)
```

### Agent Responsibilities

| Agent | File | Role |
|---|---|---|
| **Orchestrator** | `agents/orchestrator.py` | Classifies intent (10 categories), manages phase transitions, triggers human escalation |
| **Profile Builder** | `agents/profile_builder.py` | Extracts 10 profile fields through adaptive conversation; branches on family, health, occupation |
| **Recommender** | `agents/recommender.py` | Scores plans across 6 weighted dimensions; surfaces 2–3 best-fit plans with reasoning |
| **Pre-fill & Flag** | `agents/prefill_flag.py` | Maps conversation history to form fields; applies 🔴🟡🟢 flag system to high-risk questions |
| **Rejection Fighter** | `agents/rejection_fighter.py` | Parses rejection letters, classifies rejection type, cites IRDAI regulations, drafts appeal letters |

---

## 📊 Insurance Plan Database

10 curated Indian plans in `data/insurance_plans.json`:

**Health Insurance**
- Star Health Comprehensive
- HDFC Ergo Optima Restore
- Niva Bupa ReAssure 2.0
- Care Supreme
- Aditya Birla Activ Health Platinum Enhanced

**Term / Life Insurance**
- HDFC Life Click 2 Protect Super
- ICICI Prudential iProtect Smart
- Max Life Smart Secure Plus
- Tata AIA SampurnaRaksha Supreme
- LIC Tech Term Plan

Each plan includes: premium by age band, network hospital count, claim settlement ratio, pre-existing waiting period, key features, exclusions, and available riders.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | [Streamlit](https://streamlit.io) 1.51+ |
| AI / LLM | [Anthropic Claude](https://www.anthropic.com) (`claude-sonnet-4-6`) |
| PDF Parsing | [pypdf](https://pypdf.readthedocs.io) |
| Config | python-dotenv |
| Language | Python 3.10+ |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10 or higher
- An [Anthropic API key](https://console.anthropic.com/)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/suhas-gorthi/bima-buddy.git
cd bima-buddy

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API key
cp .env.example .env
# Edit .env and add your key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### Run

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

> **Alternative:** Enter your API key directly in the sidebar when the app loads — no `.env` file needed.

---

## 📁 Project Structure

```
bima-buddy/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py       # Intent routing & phase management
│   ├── profile_builder.py    # Conversational profiling agent
│   ├── recommender.py        # Plan recommendation & scoring agent
│   ├── prefill_flag.py       # Application pre-fill & flag agent
│   └── rejection_fighter.py  # Claim rejection analysis & appeal agent
│
├── data/
│   └── insurance_plans.json  # 10 curated Indian insurance plans
│
└── utils/
    └── helpers.py            # JSON extraction, text cleaning, helpers
```

---

## 🔄 Conversation Flow

```
Greeting
   │
   ▼
Profile Building  ──────────────────────────────────────────────┐
(age, family, city, income, health, occupation, risk appetite)   │
   │                                                             │
   ▼                                                             │
Plan Recommendations                                        At any point:
(2–3 ranked plans with scores, features, riders)           upload a file
   │                                                        or paste a
   ▼                                                        rejection letter
Select Plan                                                 → Rejection
   │                                                          Fighter
   ▼
Application Form
(pre-filled · flagged · rider suggestions)
   │
   ▼
Payment Page
(UPI / Card / Net Banking · GST breakdown)
   │
   ▼
Success Screen
(Policy number · Download confirmation)
```

---

## ⚔️ Rejection Fighter — Key IRDAI Regulations

The Rejection Fighter agent references these regulations when building appeals:

| Regulation | Key Point |
|---|---|
| **IRDAI 8-Year Moratorium (2020)** | After 8 continuous policy years, insurers **cannot** reject claims citing non-disclosure of pre-existing conditions |
| **Health Insurance Regulations 2016** | Pre-existing disease must be based on a physician's documented diagnosis within 48 months of policy inception |
| **Ombudsman Rules 2017** | Decisions binding on insurers for claims up to ₹30 lakhs; free for policyholders |
| **Consumer Protection Act 2019** | Unjust rejection = deficiency of service; Consumer Forum can award compensation |
| **Standard Definitions Circular** | Insurers must use standard definitions; broad exclusions without documented diagnosis are invalid |

**Win probability by rejection type:**

| Rejection Type | Estimated Win Rate |
|---|---|
| Administrative error | 85%+ |
| Pre-existing (policy > 8 years) | 75%+ |
| Document deficiency | 70%+ |
| Exclusion misapplied | 60%+ |
| Definition dispute | 65% |
| Waiting period dispute | 50% |

---

## 🔐 Security & Privacy

- The API key is stored only in your local `.env` file and never committed to version control (`.gitignore` excludes `.env`)
- No user data is persisted beyond the browser session
- All form data stays client-side (Streamlit session state)

---

## 📄 License

This project was built as a group prototype for academic/demonstration purposes.

---

*Built with ❤️ using [Claude](https://www.anthropic.com) · [Streamlit](https://streamlit.io) · [Bima Buddy](https://github.com/suhas-gorthi/bima-buddy)*
