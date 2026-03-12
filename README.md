# 🎓 AI-Powered Admission Counseling Chatbot (Advanced RAG)

This project implements an **AI-powered chatbot for university admission counseling**, leveraging the **Advanced Retrieval-Augmented Generation (Advanced RAG)** architecture to provide accurate, consistent, and context-aware answers to prospective students.

The chatbot is designed to support:
- Automated responses to admission-related FAQs
- Intelligent information retrieval from multiple admission data sources
- Reduced hallucination through retrieval-based grounding
- Scalable and modular AI system architecture

---

## 🚀 Demo
> Demo link will be added after deployment.

---

## 🧠 System Architecture Overview

The system follows an **Advanced RAG pipeline**:

1. User submits a query via the frontend
2. Backend processes the query and retrieves relevant knowledge from a vector database
3. Retrieved context is combined with a prompt
4. The Large Language Model (LLM) generates a grounded response
5. The answer is returned to the user

**Main components:**
- Frontend (User Interface)
- Backend API (RAG orchestration)
- Vector Database (semantic retrieval)
- Large Language Model (response generation)

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** – RESTful API framework
- **Advanced RAG Architecture**
- **LlamaIndex** – Indexing and retrieval management
- **Qdrant** – Vector database
- **OpenAI API** – Large Language Model
- **Python 3.10+**

### Frontend
- **Vite**
- **React**
- **TypeScript**
- **Tailwind CSS**

---

## 📂 Project Structure

