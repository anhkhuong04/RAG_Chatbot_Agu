# 🎓 AI-Powered Admission Counseling Chatbot (Advanced RAG)

This project implements an **AI-powered chatbot for university admission counseling** at **An Giang University (AGU)**, leveraging **Advanced Retrieval-Augmented Generation (Advanced RAG)** to provide accurate, consistent, and context-aware answers to prospective students.

The chatbot is designed to support:
- 🤖 Automated responses to admission-related FAQs
- 📊 Intelligent tabular data extraction for admission scores and tuition fees using Pandas Query Engines
- 🛡️ Reduced hallucination through retrieval-based grounding and strict system prompts

---

## 🚀 Demo
> Demo link will be added after deployment.

---

## 🧠 System Architecture Overview

The system follows a strict separation of concerns, ensuring high maintainability and scalability:

### Backend: Clean Architecture
The backend is structured into layers to decouple the core business logic (RAG orchestration) from external frameworks and delivery mechanisms (FastAPI, Qdrant, MongoDB).

- `app/api/`: FastAPI route handlers and request/response models.
- `app/service/`: Core business logic, intent configuration, and Advanced RAG pipelines.
- `app/db/`: Database connection singletons (MongoDB, Qdrant).
- `app/core/`: Application settings, security, and environment configurations.
- `data/`: Ingestion pipelines (LlamaParse) and structured/unstructured datasets.

### Frontend: Feature-Sliced Design (FSD)
The React frontend isolates code strictly by feature domains, eliminating monolithic hooks and components.

- `features/chat/`: Chatbot UI, Zustand global state for message management, and SSE streaming hooks.
- `features/admin/`: Admin knowledge base dashboard, React Query hooks for document and prompt API mutations.
- `features/auth/`: Authentication stores and forms.
- `lib/`: Centralized API Axios instances and Query clients.

---

## 🛠️ Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.12)
- **RAG Orchestrator:** LlamaIndex
- **Vector Database:** Qdrant
- **Conversation State DB:** MongoDB
- **LLM / Embeddings:** OpenAI
- **Data Parsing:** LlamaParse (for complex PDF & tables)

### Frontend
- **Framework:** React + Vite + TypeScript
- **Styling:** Tailwind CSS
- **Data Fetching:** TanStack React Query
- **Routing:** React Router DOM

---

## � Project Structure

```text
RAG_Chatbot_Agu/
├── Backend/
│   ├── app/                # Clean Architecture Logic
│   │   ├── api/            # FastAPI Endpoints
│   │   ├── core/           # Security & Configs
│   │   ├── db/             # Qdrant & Mongo Clients
│   │   └── service/        # RAG Engines & Chat Logic
│   ├── data/               # Ingested datasets (PDFs, CSVs)
│   ├── tests/              # Pytest verification
│   └── main.py             # Uvicorn entry point
└── Frontend/
    ├── src/
    │   ├── features/       # Feature-Sliced Design
    │   │   ├── admin/      # Admin Panel (KB, Prompts)
    │   │   ├── auth/       # Login logic
    │   │   └── chat/       # Chatbot Interface & SSE
    │   ├── lib/            # Axios & React Query clients
    │   ├── pages/          # Top-level Page components
    │   └── main.tsx        # React entry point
    ├── vite.config.ts
    └── package.json
```

---

## ⚙️ Local Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/anhkhuong04/RAG_Chatbot_Agu.git
cd RAG_Chatbot_Agu
```

### 2. Backend Setup
```bash
cd Backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
> **Note:** Copy `.env.example` to `.env` and fill in your API keys (Gemini, Qdrant, MongoDB).

Run the API:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd Frontend
npm install
```
> **Note:** Create `.env` in the `Frontend` directory with `VITE_API_URL=http://localhost:8000`.

Run the Dev Server:
```bash
npm run dev
```

---

## �️ License
This project is proprietary and built for An Giang University admission counseling purposes.
