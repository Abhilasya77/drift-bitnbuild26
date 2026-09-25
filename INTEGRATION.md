# Integration guide (credential + QR + Web3 + integration owner)

## How the pieces connect

```
frontend (React/Vite, Vercel) ──HTTP──▶ backend (FastAPI, Render)
      │ supabase-js login                 ├─ Supabase Postgres + private Storage
      │                                   ├─ ml/consistency.py   (AI/ML teammate)
      │                                   ├─ Tesseract OCR
      │                                   ├─ CompreFace / simulated biometric
      └─ /verify/:token page ─────────────┴─ Polygon Amoy contract (hash only)
```

## Order to connect things (each step works on its own)

1. **Backend local:** `pytest -q` passes, `uvicorn app.main:app --reload` → `/docs` works (AUTH_MODE=dev)
2. **Frontend ↔ backend local:** the frontend calls `http://127.0.0.1:8000` with the header `X-Demo-User` (snippet below)
3. **Consistency engine:** the AI/ML teammate's changes go in `backend/ml/consistency.py`; rerun `pytest -q`
4. **Web3:** deploy the contract (blockchain/README.md) → put 3 values in `backend/.env` → issue a credential → check the explorer link
5. **Supabase:** switch `AUTH_MODE=supabase`, `STORAGE_MODE=supabase`, `DATABASE_URL` → the frontend sends the Supabase token instead
6. **Deploy:** backend to Render (Docker), frontend to Vercel; set `VITE_API_URL` and `VERIFY_BASE_URL`
7. **Biometric:** CompreFace only if time allows; otherwise the labelled simulated check

## Frontend API helper (give this to the frontend teammate)

```js
// src/api.js
import { supabase } from "./supabase";        // only needed once AUTH_MODE=supabase
const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const DEV_USER = import.meta.env.VITE_DEV_USER; // e.g. ravi@drift.demo while AUTH_MODE=dev

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (DEV_USER) headers["X-Demo-User"] = DEV_USER;
  else {
    const { data } = await supabase.auth.getSession();
    if (data.session) headers["Authorization"] = `Bearer ${data.session.access_token}`;
  }
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { method, headers, body: form ?? (body && JSON.stringify(body)) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const d = err.detail;   // FastAPI errors: a string, or {message, missing} for eligibility
    throw new Error(typeof d === "string" ? d : d?.message || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}
// upload: const f = new FormData(); f.append("document_type","passport"); f.append("file", file);
//         await api("/documents", { method: "POST", form: f });
```

**QR image:** it's behind login, so fetch it with the same headers and show it as a blob:
```js
const res = await fetch(API + "/credentials/current/qr", { headers });   // same headers as above
img.src = URL.createObjectURL(await res.blob());
```

**Verify page** (`/verify/:token`, no login): `GET /verify/{token}` shows the state, biometric, conflicts, expiry and the on-chain link. The name box calls `POST /verify/{token}/name` with `{ "name": "..." }`.

## Environment variables

| Where | Variable | Local | Deployed |
|---|---|---|---|
| backend | `AUTH_MODE` | dev | supabase |
| backend | `STORAGE_MODE` | local | supabase |
| backend | `DATABASE_URL` | sqlite:///./dev.db | Supabase session-pooler URI |
| backend | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | – | from Supabase |
| backend | `REVIEWER_EMAILS` | reviewer@drift.demo | reviewer account email(s) |
| backend | `CREDENTIAL_SECRET` | any long random text | long random text |
| backend | `VERIFY_BASE_URL` | http://localhost:5173/verify | https://<vercel-app>/verify |
| backend | `CORS_ORIGINS` | * | https://<vercel-app> |
| backend | `WEB3_RPC_URL`, `WEB3_CONTRACT_ADDRESS`, `WEB3_PRIVATE_KEY` | optional | optional |
| frontend | `VITE_API_URL` | http://127.0.0.1:8000 | https://<render-app> |
| frontend | `VITE_DEV_USER` | ravi@drift.demo | (remove) |
| frontend | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | – | from Supabase (anon key only!) |

Secrets (`SUPABASE_SERVICE_ROLE_KEY`, `WEB3_PRIVATE_KEY`, `CREDENTIAL_SECRET`) live only in the backend `.env` / Render settings.

## Before judging (checklist)

- [ ] Open the Render `/health` 2 minutes before, so it wakes up (free tier sleeps)
- [ ] Demo accounts ready: Ravi (happy path), Priya (review path), reviewer
- [ ] Synthetic documents from `backend/demo/docs/` are on the demo laptop
- [ ] One credential already issued, and its explorer link opens
- [ ] Backup: backend running locally + a recorded demo video
