# KGRCET RAG Assistant — React + FastAPI

This adds a web interface to the existing KGRCET RAG project. It **opens the existing**
`chroma_db` folder and `kgrcet_website` collection. It does not crawl, chunk, or re-index data.

## Before you start

Run these commands from the existing project root (the folder that already contains
`chroma_db`, `.env`, and `query_data.py`).

## 1. Install backend packages

Activate your existing virtual environment if it is not already active:

### Windows PowerShell
```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi "uvicorn[standard]" chromadb sentence-transformers groq python-dotenv
```

If PowerShell blocks activation, you can skip activation and use:
```powershell
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" chromadb sentence-transformers groq python-dotenv
```

## 2. Check the project-root `.env`

The `.env` file should contain the API key and the model ID that worked in your existing app.
Do not paste or commit the key.

```dotenv
GROQ_API_KEY=your_private_key_here
GROQ_MODEL=openai/gpt-oss-120b
CHROMA_COLLECTION=kgrcet_website
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Use the model ID available to your Groq account. If your existing working `query_data.py`
uses a different model ID, keep that working ID in `GROQ_MODEL`.

## 3. Install frontend packages

Open a **second** VS Code terminal, from the project root:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the local URL Vite prints (normally `http://localhost:5173`).

## 4. Start the backend

In the first VS Code terminal, from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

If activation is blocked:
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Test:
- API health: http://127.0.0.1:8000/health
- Database readiness: http://127.0.0.1:8000/ready
- Interactive API docs: http://127.0.0.1:8000/docs
- Frontend: http://localhost:5173

The `/ready` response should show collection `kgrcet_website` and your indexed chunk count (expected: 1309).

## Important notes

- Do not run `index_data.py`, `collect_website.py`, or `process_documents.py` for this frontend setup.
- Do not put `GROQ_API_KEY` in `frontend/.env`. Only `VITE_API_BASE_URL` belongs there.
- The backend uses `collection.query(...)` and `get_collection(...)`, not `get_or_create_collection(...)`; it does not create or modify the collection.
- If your collection's metadata uses a different URL key, update the metadata keys list in `backend/rag_service.py`.
- The app keeps chat history in React memory for the current browser session; refreshing the page clears that chat history.
- The frontend and backend are intended for local development. Before public deployment, add authentication, rate limiting, and suitable server-side CORS settings.
