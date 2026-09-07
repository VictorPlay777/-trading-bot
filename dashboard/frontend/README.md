# Bybit Bot Panel frontend

Run the dashboard backend on port 8080, then start the frontend:

```bash
npm install
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8080`.

Build for FastAPI static serving:

```bash
npm run build
```

The output is written to `dashboard/frontend/dist`, which the FastAPI backend serves when present.
