# Backend: Identity Continuity Platform (Team Drift)

FastAPI API that runs the whole identity flow:

**document upload → OCR → cross-document consistency → exception-only human review → biometric check → server-side eligibility → temporary credential + QR → service verification → renewal / permanent-ID switch**

Follows the team's *Backend Schema* and *TDR* docs: Supabase (auth, Postgres, storage), Tesseract OCR, RapidFuzz matching, CompreFace face verification, QR credential, optional Polygon Amoy attestation.

## Run it on your laptop (5 minutes, no Supabase needed)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
brew install tesseract          # optional, for real OCR (Mac). Without it, users type the fields.
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs**. In local mode, every call needs the header `X-Demo-User: someone@example.com`, which is your fake login. Use `reviewer@drift.demo` to act as the reviewer.

Run the full demo story as a test: `pytest -q -s` (Ravi happy path + Priya forged-DOB review path).

Make the synthetic demo documents: `python demo/make_demo_docs.py`, which writes the images to `demo/docs/`.

## Folder map

| Path | What it is | Owner |
|---|---|---|
| `app/main.py` | App entry, `/health` | Backend |
| `app/models.py` | All 13 tables from the schema doc | Backend |
| `app/workflow.py` | Evaluation, review routing, eligibility, credential state, next action | Backend |
| `app/routers/` | API routes (one file per area) | Backend |
| `app/services/ocr.py` | Tesseract + passport MRZ check digits | Backend / ML |
| `app/services/biometric.py` | CompreFace adapter (simulated if not configured) | Biometric |
| `app/services/credentials.py` + `app/routers/credentials.py` | Credential ID, QR, verify page API, name check | Credential/Web3/Integration |
| `app/services/web3_attest.py` | Writes/revokes/reads the hash on Polygon Amoy | Credential/Web3/Integration |
| `ml/consistency.py` | **Identity Consistency Engine** (RapidFuzz + rules) | **AI/ML teammate** |
| `demo/make_demo_docs.py` | Synthetic SPECIMEN documents | Demo |
| `tests/test_flow.py` | End-to-end demo story | Everyone |

**AI/ML teammate:** improve `ml/consistency.py` (variant tables, rules, scoring) but keep the function names and return shapes. Test ideas quickly with `POST /consistency/compare-names`.

## API (what each frontend screen calls)

| Screen | Calls |
|---|---|
| Dashboard | `GET /profiles/me` (status of every stage + `next_action` + document health) |
| Identity Profile | `POST /profiles`, `PATCH /profiles/me` |
| Documents | `POST /documents` (multipart: `document_type`, `file`), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/file` |
| Processing | `POST /documents/{id}/process` (OCR) → show fields → `POST /documents/{id}/confirm-fields` |
| Consistency Report | `POST /consistency/evaluate`, `GET /consistency/latest` |
| Biometric | `POST /biometric/start` (multipart `selfie`), `GET /biometric/status` |
| Eligibility | `GET /eligibility` (checklist) |
| My Credential | `POST /credentials`, `GET /credentials/current`, `GET /credentials/current/qr` (PNG) |
| Service Verification (public) | `GET /verify/{token}`, `POST /verify/{token}/name` |
| Document Health | `POST /documents/{id}/renewal`, upload the new one with `replaces_document_id`, `GET /documents/{id}/compare-previous` |
| Permanent ID | upload with `is_permanent_credential=true` → confirm fields → `POST /permanent-credential` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/run-expiry-check` (demo) |
| Reviewer Dashboard | `GET /reviews`, `GET /reviews/stats`, `GET /reviews/{id}`, `POST /reviews/{id}/request-evidence`, `POST /reviews/{id}/resolve` |
| Blockchain | Automatic: with `WEB3_*` set, issuing writes the hash on Polygon Amoy and linking the permanent ID revokes it. `/credentials/current` and `/verify/{token}` show the tx + explorer link. (Manual MetaMask alternative: `GET /credentials/current/attestation-payload` → send tx → `POST /credentials/current/attestation`.) |

Enum values are listed in `app/models.py` comments.

## Switching to Supabase (real login, database and storage)

1. Supabase project → **Storage** → new **private** bucket `identity-evidence`
2. In `.env`: set `AUTH_MODE=supabase`, `STORAGE_MODE=supabase`, `DATABASE_URL` (Project Settings → Database → Connection string → *Session pooler* URI), `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
3. Restart. Tables are created automatically, with Row Level Security switched on, so nobody can read them through Supabase's public API. Only this backend can.
4. Frontend: sign up / sign in with `supabase-js`, then call this API with `Authorization: Bearer <session.access_token>`
5. Reviewer accounts: add their emails to `REVIEWER_EMAILS`

## CompreFace (real face verification, optional)

```bash
git clone https://github.com/exadel-inc/CompreFace && cd CompreFace && docker compose up -d
```
Open http://localhost:8000 → create an application → add a **Verification** service → copy its API key into `COMPREFACE_API_KEY`, and set `COMPREFACE_URL=http://localhost:8000`. Run our API on another port: `uvicorn app.main:app --reload --port 8001`. Without CompreFace, the step is a clearly labelled **simulated** check.

## Deploy (Render)

New → Web Service → this repo → Root Directory `backend` → Runtime **Docker** (installs Tesseract) → add the `.env` values as environment variables. Free instances sleep after 15 minutes, so open `/health` a minute before judging.

## Boundaries (say these in the Q&A)

- Documents agreeing with each other ≠ proof they are authentic. The MRZ check only catches edits to machine-readable fields.
- The biometric step is a prototype face verification (CompreFace or simulated), not an official UAE check, and not liveness detection.
- The temporary credential is platform-issued, not a government ID. Each service applies its own policy.
- Only a non-sensitive hash goes on-chain. Selfies are never stored. Use synthetic demo documents.
