# CSV Insights Agent

CSV Insights Agent turns an uploaded CSV and a plain-language question into key insights, interactive visualizations, and actionable next steps. It uses an OpenAI-compatible language model when configured and otherwise remains fully usable through deterministic pandas analysis.

## Quick start

Run the backend and frontend in two terminals.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, activate the environment with `.\.venv\Scripts\Activate.ps1` and use `Copy-Item .env.example .env`. The API is available at <http://localhost:8000> and its documentation at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>. For production, run `npm run build` followed by `npm start`.

The frontend intentionally uses only Next.js, React, TypeScript, Chart.js, and their type packages. This dependency-minimal setup supports restricted corporate npm environments.

## Try it out

1. Choose `sample_data/learning_demo.csv`.
2. Enter **Show me participation, completion, and assignment completion by course.**
3. Select **Analyze**.
4. Explore the three result panels. A next-step card runs a follow-up analysis using the same CSV.

## Environment variables

### Backend (`backend/.env`)

| Name | Default | Description |
| --- | --- | --- |
| `LLM_API_KEY` | `sk-your-key-here` | Optional language-model API key; the placeholder uses pandas analysis. |
| `LLM_BASE_URL` | `https://llm.maqsoftware.net/v1` | Base URL for the OpenAI-compatible API. |
| `LLM_MODEL` | `qwen-3.6-27b` | Model used for generated insights and next steps. |
| `DATABASE_PATH` | `data/insights.db` | SQLite path relative to `backend/`. |
| `UPLOADS_DIR` | `uploads` | Uploaded-file directory relative to `backend/`. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins allowed to call the API. |

### Frontend (`frontend/.env.local`)

| Name | Default | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | FastAPI URL used by the Next.js `/api` rewrite. |

## Tests

```bash
cd backend && pytest
cd frontend && npm run typecheck && npm run build
```
