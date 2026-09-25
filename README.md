# BhoomiAI — Stage 1: Local Research Assistant

Free-tools-only SIH starter. Includes a FastAPI backend, PostgreSQL + pgvector, local embedding model, local Ollama LLM, PDF/TXT/MD ingestion and a React frontend. **This is a development prototype, not the complete national platform.** GIS, policy simulation, collaboration and the innovation portal come in later stages.

## Prerequisites
Windows 11, Python 3.11 or 3.12, Node.js 20+, Docker Desktop (WSL 2), Ollama. Download dependencies and models while online. No paid API is required.

## 1. Start PostgreSQL
From the repository root:
```powershell
docker compose up -d
docker compose ps
```
PostgreSQL is mapped to localhost:5433; the password is development-only. Never expose this service publicly.

## 2. Download the local LLM
```powershell
ollama pull gemma3:4b
ollama run gemma3:4b
```
If your laptop runs out of memory, try `ollama pull gemma3:1b` and set `OLLAMA_MODEL=gemma3:1b` in backend/.env.

## 3. Start the Python backend
Open a PowerShell terminal at the repository root:
```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
If Python 3.11 is not installed but 3.12 is, replace `py -3.11` with `py -3.12`. If PowerShell blocks activation: `Set-ExecutionPolicy -Scope Process Bypass`. The embedding model downloads on first use.

API docs: http://localhost:8000/docs
Health: http://localhost:8000/health

## 4. Start the frontend
In a second terminal, from repository root:
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 . Upload sample_documents/demo_only_land_research.txt and ask a question about the example note.

## API endpoints
- GET /health: check DB connection
- POST /documents: upload PDF/TXT/MD (15 MB maximum)
- GET /documents: list indexed docs
- GET /search?q=...: vector similarity retrieval
- POST /chat with JSON {"question":"..."}: locally generated source-grounded answer

## Safety and current limitations
The example document is fictional. Verify cited material. The app only stores extracted text, not original PDFs; retain permitted source copies separately. Scanned PDF OCR, access control, data licensing review, GIS, policy simulations and large-scale indexing are not included yet. Do not expose this development prototype publicly or upload personal landowner information.

## Next stages
1. Add document metadata and state/district filters.
2. Integrate PostGIS, Leaflet and open-licensed geospatial datasets.
3. Add a transparent scenario-based land-use analytics module.
4. Add collaboration and access controls.
5. Add evidence-linked retrieval and research-gap analysis.
