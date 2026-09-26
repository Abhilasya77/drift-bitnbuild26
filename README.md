# Tawashir

**Team Drift · BitNBuild '26 (UAE Regional Round)**

> *You don't have one name. You have one identity with several names, and we accept all of them.*

Tawashir is a web platform that establishes a person's identity from several documents, explains why their names differ across those documents instead of rejecting them, sends only genuinely unclear cases to a human reviewer, and issues a **temporary, verifiable credential** that bridges the gap while a permanent ID (e.g. Emirates ID) is pending or being renewed.

| | Link |
|---|---|
| 🌐 Live app | https://drift-bitnbuild26.vercel.app |
| ⚙️ Live API (Swagger docs) | https://drift-backend-oemw.onrender.com/docs |
| ⛓️ Attestation contract (Polygon Amoy) | [`0xB292a0b992B1F90e6B2374bA45Dba3f678F2e036`](https://amoy.polygonscan.com/address/0xB292a0b992B1F90e6B2374bA45Dba3f678F2e036) |

**Demo login:** `demo@tawashir.io` / `Tawashir@2026` (or sign up with any email).
**Reviewer view:** open `review.html` from the sidebar ("Reviewer view").

---

## The problem

A worker in the UAE can hold a passport that says **"Amrita Kalra"**, a visa that says **"Amrita Kalra Gurbaksh Singh"** (father's name added) and an Emirates ID with yet another variation. In a [real case reported by Gulf News](https://gulfnews.com/uae/reader-complaints/uae-help-dh50000-stuck-with-money-exchange-due-to-the-name-format-on-my-passports-visa-page-1.1656071416510), a Dh50,000 transfer from Kuwait was held at a Dubai exchange house until the sender changed the beneficiary name. Today's fixes are manual and single-use: affidavits, name amendments, office visits.

## How we address the three problem statements, with one workflow

| Problem statement | What breaks | What Tawashir does |
|---|---|---|
| **Forms that reject real names** (Web) | Forms force first/last name, cut or reorder names, and reject valid variants | One flexible "name as you use it" field (any script). The consistency engine **explains** differences (father's name appended, spacing, word order, initials, transliteration, single-name `FNU`) instead of requiring an exact string match |
| **Verification assumes settled residency** (Blockchain) | New arrivals, renewals and moves create gaps where no valid ID is accepted | A **temporary platform credential** with a QR code covers the gap, stays valid during a document renewal, and retires automatically when the permanent ID is linked. Its fingerprint is **attested on Polygon Amoy**, so any service can verify it without trusting our database |
| **Approval fatigue** (AI/ML) | Reviewers see hundreds of harmless mismatches and start rubber-stamping | Routine differences are cleared automatically. **Only uncertain/conflicting cases** reach a reviewer, with the exact field highlighted. Passport **MRZ check digits** catch edited fields a tired human would miss |

## User journey

1. **Sign up** → create an identity profile (self-declared)
2. **Upload documents**: passport, visa/residence, national/GCC ID (primary); Grade 10/12 certificates (supporting)
3. **OCR** reads each document (passport MRZ + Tesseract), and the user confirms the fields
4. **Consistency report**: every field compared across documents → *Match / Explainable variant / Uncertain / Conflict*, each with a plain-language explanation
5. **Human review** only if needed (reviewer sees just the flagged fields)
6. **Biometric check**: face verification against the document photo (CompreFace; a clearly labelled simulation when not configured)
7. **Server-side eligibility** → **temporary credential + QR**, hash attested on-chain
8. **Service verification**: a bank scans the QR and can check whether a name (e.g. a visa-style beneficiary name) is supported by the person's verified documents
9. **Document health**: expiry reminders, "renewal in progress", permanent ID arrives → linked, temporary credential expired and revoked on-chain

## Architecture

```
Frontend (HTML/CSS/JS, Vercel) ──HTTPS──▶ FastAPI backend (Docker on Render)
                                            ├─ SQLite (demo) / Supabase Postgres
                                            ├─ Tesseract OCR + passport MRZ check digits
                                            ├─ Identity Consistency Engine (RapidFuzz + rules)
                                            ├─ Exception-only review queue
                                            ├─ CompreFace face verification (or labelled simulation)
                                            ├─ Credential service (QR, verification, lifecycle)
                                            └─ web3.py ──▶ CredentialAttestation.sol on Polygon Amoy
```

| Area | Tech |
|---|---|
| Frontend | Vanilla HTML/CSS/JS (no build step), Font Awesome |
| Backend | Python, FastAPI, SQLAlchemy, Pydantic |
| AI/ML | RapidFuzz + rule engine, Tesseract OCR, ICAO 9303 MRZ validation |
| Biometric | CompreFace (face verification REST API) |
| Blockchain | Solidity 0.8.24, Polygon Amoy testnet, web3.py, Remix |
| Deploy | Render (backend, Docker), Vercel (frontend) |

## Repository layout

```
frontend/     landing page, auth, live app (app.html), verifier (verify.html), reviewer (review.html)
backend/      FastAPI app, consistency engine (ml/), OCR/biometric modules, tests, demo scripts
blockchain/   CredentialAttestation.sol, compile + deploy scripts
docs/         project documents
INTEGRATION.md  how the pieces connect
```

## Run it locally

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m pytest -q                       # 4 passed: full demo story + on-chain test on a local chain
uvicorn app.main:app --reload --port 8001 # API docs: http://127.0.0.1:8001/docs

# frontend (new terminal)
cd frontend && python3 -m http.server 5500   # http://localhost:5500
```

Synthetic demo documents (clearly marked SPECIMEN) are in `frontend/demo-docs/` and `backend/demo/docs/`. The app has one-click buttons to use them.

## Privacy and honest boundaries

- **No personal data on-chain**: only a hash of {credential id, issue/expiry dates, issuer}
- **Selfies are never stored**: only the verification result
- The QR code contains an opaque token, not personal data; verifiers see only a minimal result
- Documents agreeing with each other **does not prove they are authentic**; MRZ checks catch edited machine-readable fields only
- The biometric step is a prototype face verification, **not** an official UAE biometric check or liveness detection
- The temporary credential is platform-issued and **not a government ID**; each service applies its own policy
- Only synthetic demo documents are used

## Team Drift

Built in 36 hours for BitNBuild '26 by Team Drift (GDGoC BITS Pilani Dubai round).
