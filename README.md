# CSV Insights Agent

Upload a CSV and receive key insights, interactive visualizations, and actionable next steps.

## Frontend

The frontend is a dependency-minimal Next.js App Router application. It intentionally uses only Next.js, React, TypeScript, Chart.js, and their type packages so it can be installed in restricted corporate npm environments.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Production commands are `npm run build` and `npm start`.

### Quick start

In one terminal, start the existing FastAPI backend on port 8000. In another:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | FastAPI API base URL used by the development rewrite. |

The application works without `LLM_API_KEY`, using deterministic pandas analysis when the backend is configured for it.
