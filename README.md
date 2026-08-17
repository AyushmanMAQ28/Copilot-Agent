# CSV Insights Agent

CSV Insights Agent turns an uploaded CSV and a plain-language question into three useful outputs:

- **Key Insights** — concise findings from the data
- **Data Visualizations** — an interactive chart that can be expanded or exported
- **Next Steps** — clickable recommendations that run a follow-up analysis

The app can use an OpenAI-compatible language model when a key is configured. Without a key, it remains fully usable through its deterministic pandas analysis.

## Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer
- npm

## Quick start

Keep the backend and frontend running at the same time in **two separate terminals**.

### 1. Backend

1. Open a terminal at the repository root and enter the backend directory:

   ```bash
   cd backend
   ```

2. Create and activate a virtual environment.

   **macOS/Linux**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows PowerShell**

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the example configuration:

   **macOS/Linux**

   ```bash
   cp .env.example .env
   ```

   **Windows PowerShell**

   ```powershell
   Copy-Item .env.example .env
   ```

5. Open `.env` and replace `sk-your-key-here` with your LLM API key. You may leave the placeholder in place to use the built-in pandas fallback.

6. Start the API:

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

The API is available at <http://localhost:8000>, with interactive documentation at <http://localhost:8000/docs>.

### 2. Frontend

1. Open a **second terminal** at the repository root:

   ```bash
   cd frontend
   npm install
   ```

2. Copy the example configuration:

   **macOS/Linux**

   ```bash
   cp .env.example .env
   ```

   **Windows PowerShell**

   ```powershell
   Copy-Item .env.example .env
   ```

3. Start the Vite development server:

   ```bash
   npm run dev
   ```

Open <http://localhost:5173> in a browser.

## Try it out

1. Choose `sample_data/learning_demo.csv`.
2. Enter: **Show me participation, completion, and assignment completion by course.**
3. Select **Analyze CSV**.
4. Explore the three result panels. A next-step card can be selected to run another analysis.

## Environment variables

### Backend (`backend/.env`)

| Name | Default | Description |
| --- | --- | --- |
| `LLM_API_KEY` | `sk-your-key-here` | Optional language-model API key. The placeholder activates the pandas fallback. |
| `LLM_BASE_URL` | `https://llm.maqsoftware.net/v1` | Base URL for the OpenAI-compatible API. |
| `LLM_MODEL` | `qwen-3.6-27b` | Model used for generated insights and next steps. |
| `DATABASE_PATH` | `data/insights.db` | SQLite path, resolved relative to `backend/`. |
| `UPLOADS_DIR` | `uploads` | Uploaded-file directory, resolved relative to `backend/`. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins allowed to call the API. |

### Frontend (`frontend/.env`)

| Name | Default | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | API URL used by the browser. `/api` uses the local Vite proxy. |
| `LLM_API_KEY` | `sk-your-key-here` | Inert placeholder kept for configuration consistency; browser code does not read or expose it. |

## Project structure

```text
.
├── backend/
│   ├── app/                 # FastAPI routes, configuration, and analysis
│   ├── tests/               # Backend API tests
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/                 # React user interface
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts       # Port 5173 and local /api proxy
├── sample_data/
│   └── learning_demo.csv
└── README.md
```

SQLite data and uploads are created automatically inside `backend/` on first startup.

## Running tests

Backend:

```bash
cd backend
pytest
```

Frontend build and type-check:

```bash
cd frontend
npm run build
npx tsc --noEmit
```

## Troubleshooting

- **Port already in use:** Stop the process using port 8000 or 5173, then restart that server. You can identify it with `lsof -i :8000` or `lsof -i :5173` on macOS/Linux, or `Get-NetTCPConnection -LocalPort 8000,5173` in PowerShell.
- **Missing or invalid `LLM_API_KEY`:** The app still works with deterministic pandas-only analysis. Set a valid key in `backend/.env` when generated language-model responses are needed.
- **CORS error:** Confirm the frontend is at `http://localhost:5173`, the backend is at `http://localhost:8000`, and `CORS_ORIGINS` contains the exact frontend origin. Restart the backend after changing `.env`.
- **Upload rejected:** Only files ending in `.csv` are accepted. Export spreadsheet data as CSV first; empty files and files larger than 10 MB are also rejected.
