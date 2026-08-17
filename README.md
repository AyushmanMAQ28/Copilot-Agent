# CSV Insights Agent

CSV Insights Agent turns an uploaded CSV and a plain-language question into key insights, data visualizations, and actionable next steps.

The backend is FastAPI + pandas + SQLite. The frontend is plain HTML/CSS/vanilla JavaScript served directly by FastAPI (no npm, no build step).

## Prerequisites

- Python 3.11+
- No Node.js required

## Quick start (single terminal)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>.

On Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Frontend development

There is no frontend build pipeline.

- Edit files under `backend/app/static/`
- Refresh the browser

## Project structure

```text
backend/
  app/
    analysis.py
    config.py
    main.py
    static/
      index.html
      css/
      js/
      assets/
  tests/
sample_data/
README.md
```

## Environment variables (`backend/.env`)

| Name | Default | Description |
| --- | --- | --- |
| `LLM_API_KEY` | `sk-your-key-here` | Optional model API key. If missing, deterministic pandas analysis is used. |
| `LLM_BASE_URL` | `https://llm.maqsoftware.net/v1` | OpenAI-compatible base URL. |
| `LLM_MODEL` | `qwen-3.6-27b` | Model for generated insights/next steps. |
| `DATABASE_PATH` | `data/insights.db` | SQLite path relative to `backend/`. |
| `UPLOADS_DIR` | `uploads` | Upload directory relative to `backend/`. |
| `CORS_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Comma-separated allowed browser origins. |

## Try it out

1. Upload `sample_data/learning_demo.csv`.
2. Ask: **Show me participation, completion, and assignment completion by course.**
3. Review the three-column workspace:
   - Key Insights (left)
   - Data Visualizations (center)
   - Next Steps (right)

## Testing

```bash
cd backend
pytest
```

## Troubleshooting

- **Port already in use**: run `uvicorn app.main:app --reload --port 8001`.
- **CSV rejected**: only `.csv` uploads are accepted.
- **No LLM output**: check `LLM_API_KEY`; app automatically falls back to deterministic pandas analysis.
- **UI changes not visible**: hard refresh browser (Ctrl/Cmd+Shift+R).
