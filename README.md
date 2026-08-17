# CSV Insights Agent

CSV Insights Agent turns a CSV upload into defensible data-quality findings, interactive visualizations, and follow-up questions. It is designed to remain useful without an LLM key: the backend always produces a deterministic pandas analysis.

## Architecture

The React 18/Vite frontend proxies `/api` to a FastAPI service. FastAPI stores projects, chats, datasets, and analyses in SQLite; pandas performs CSV profiling and safe server-side chart aggregation. An optional OpenAI-compatible MAQ endpoint receives a compact profile, never raw CSV contents.

## Quick start

```bash
docker compose up --build
```

Open `http://localhost:5173` (or the Docker frontend port). Upload `sample_data/learning_demo.csv`.

### Local development

```bash
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# separate shell
cd frontend && npm install && npm run dev
```

Copy `backend/.env.example` to `backend/.env` to configure the optional model. Do not commit that file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | empty | MAQ OpenAI-compatible bearer token |
| `LLM_BASE_URL` | `https://llm.maqsoftware.net/v1` | model endpoint |
| `LLM_DEFAULT_MODEL` | `qwen-3.6-27b` | primary model |
| `LLM_FALLBACK_MODEL` | `gemma-4-31b` | fallback model |
| `MAX_UPLOAD_BYTES` | `52428800` | CSV size limit |
| `MAX_CSV_ROWS` | `100000` | row limit |

## API

`GET /api/health`, `GET /api/models`, project CRUD at `/api/projects`, dataset upload/listing at `/api/projects/{id}/datasets`, and analysis at `POST /api/chats/{id}/analyze` are the primary UI APIs. Dataset uploads accept only validated CSV files (extension, MIME, encoding, delimiter, and content sniffing checks). Exports are available through `/api/analyses/{id}/export/*`.

## Screenshots

The application intentionally uses a neutral slate interface rather than copying the reference demo. Its central workspace contains **Key insights**, **Data visualizations**, and **Next steps**, with chart expansion and PNG download controls.

## Troubleshooting

- **“Please select a CSV”**: Excel, PDFs, and images are intentionally rejected. Export spreadsheet data to CSV first.
- **No model key**: This is expected; a visible local/deterministic analysis remains available.
- **Frontend cannot reach API**: run FastAPI on port 8000, or set `VITE_API_URL`.
- **Large file rejected**: increase the documented upload/row limits only when sufficient memory is available.
