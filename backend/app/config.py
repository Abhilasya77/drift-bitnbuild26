"""All settings come from environment variables (put them in backend/.env).

Nothing secret is hard-coded here. See .env.example for the full list.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


# --- Database ---------------------------------------------------------------
# Local dev: SQLite file. Production: the Supabase Postgres connection string
# (Project Settings -> Database -> Connection string -> URI, "Session pooler").
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
for _prefix in ("postgres://", "postgresql://"):       # Supabase gives postgresql://...; use the psycopg 3 driver
    if DATABASE_URL.startswith(_prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_prefix):]

# --- Auth -------------------------------------------------------------------
# "dev"      -> no Supabase needed; send header  X-Demo-User: someone@example.com
# "supabase" -> frontend sends  Authorization: Bearer <supabase access token>
AUTH_MODE = os.getenv("AUTH_MODE", "dev").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")  # backend only, never in frontend
REVIEWER_EMAILS = _list("REVIEWER_EMAILS")          # e.g. reviewer@drift.demo
VERIFIER_EMAILS = _list("VERIFIER_EMAILS")          # optional service_verifier accounts

# --- Storage ----------------------------------------------------------------
# "local"    -> files go to backend/local_uploads (gitignored)
# "supabase" -> private Supabase Storage bucket
STORAGE_MODE = os.getenv("STORAGE_MODE", "local").lower()
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "identity-evidence")
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "local_uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}

# --- Biometric (CompreFace) -------------------------------------------------
# Leave COMPREFACE_URL empty to use the clearly-labelled simulated provider.
COMPREFACE_URL = os.getenv("COMPREFACE_URL", "").rstrip("/")   # e.g. http://localhost:8000
COMPREFACE_API_KEY = os.getenv("COMPREFACE_API_KEY", "")        # a *verification* service key
BIOMETRIC_THRESHOLD = float(os.getenv("BIOMETRIC_THRESHOLD", "0.85"))

# --- Credentials ------------------------------------------------------------
CREDENTIAL_SECRET = os.getenv("CREDENTIAL_SECRET", "change-me-in-env")
CREDENTIAL_DAYS = int(os.getenv("CREDENTIAL_DAYS", "90"))
# Where the QR code points. Usually the frontend verification page.
VERIFY_BASE_URL = os.getenv("VERIFY_BASE_URL", "http://localhost:5173/verify").rstrip("/")

# --- Web3 (optional, Polygon Amoy testnet) --------------------------------
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL", "")                      # e.g. https://rpc-amoy.polygon.technology
WEB3_PRIVATE_KEY = os.getenv("WEB3_PRIVATE_KEY", "")              # TESTNET-ONLY wallet, backend .env only
WEB3_CONTRACT_ADDRESS = os.getenv("WEB3_CONTRACT_ADDRESS", "")    # deployed CredentialAttestation
WEB3_CHAIN_ID = int(os.getenv("WEB3_CHAIN_ID", "80002"))          # Polygon Amoy
WEB3_NETWORK = os.getenv("WEB3_NETWORK", "polygon-amoy")
WEB3_EXPLORER_URL = os.getenv("WEB3_EXPLORER_URL", "https://amoy.polygonscan.com").rstrip("/")

# --- Reminders --------------------------------------------------------------
REMINDER_DAYS = [int(x) for x in os.getenv("REMINDER_DAYS", "30,7").split(",")]

# --- CORS -------------------------------------------------------------------
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
