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

## Sample datasets

`sample_data/` also contains four large, fully synthetic Excel workbooks that mimic
real-world business exports. Every value is generated, so the files contain no
personal or customer data.

| File | Rows | Columns | Scenario |
| --- | --- | --- | --- |
| `retail_sales_transactions.xlsx` | 48,000 | 15 | Retail and e-commerce orders with channel, region, product, discount, and return data. |
| `hospital_patient_encounters.xlsx` | 36,000 | 14 | Hospital admissions with department, diagnosis, length of stay, charges, and readmissions. |
| `hr_employee_directory.xlsx` | 32,000 | 16 | Workforce records with department, level, tenure, compensation, and attrition flags. |
| `banking_transactions.xlsx` | 50,000 | 13 | Retail banking transactions with channel, merchant category, running balance, and fraud flags. |

Each workbook uses a frozen, filterable header row, seasonal date patterns, correlated
columns, and a small share of blank values so grouping, trend, and data-quality
questions return meaningful answers.

The API accepts CSV uploads, so save a workbook as CSV in Excel or regenerate the
datasets in CSV form before analyzing them:

```bash
pip install openpyxl
python sample_data/generate_sample_data.py --format csv
```

The generator uses fixed seeds, so `--format xlsx` (the default), `--format csv`, and
`--format both` always reproduce the same rows.

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
