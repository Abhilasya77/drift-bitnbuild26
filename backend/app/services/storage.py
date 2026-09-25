"""Private file storage for uploaded demo documents.

STORAGE_MODE=local    -> backend/local_uploads/ (gitignored). Good for your laptop.
STORAGE_MODE=supabase -> private Supabase Storage bucket via its REST API (use this on Render,
                         whose disk is wiped on restart).
Object path: {user_id}/{profile_id}/{document_id}/{safe_filename}  (schema doc section 6)
"""
import os
import re
from pathlib import Path

import httpx
from fastapi import HTTPException

from .. import config


def safe_filename(name: str | None, mime: str) -> str:
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}.get(mime, "")
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", Path(name or "file").stem)[:40] or "file"
    return stem + ext   # never trust the original extension


def _headers(content_type: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}", "apikey": config.SUPABASE_SERVICE_ROLE_KEY}
    if content_type:
        h["Content-Type"] = content_type
    return h


def save(path: str, data: bytes, mime: str) -> None:
    if config.STORAGE_MODE == "supabase":
        r = httpx.post(
            f"{config.SUPABASE_URL}/storage/v1/object/{config.STORAGE_BUCKET}/{path}",
            headers={**_headers(mime), "x-upsert": "true"}, content=data, timeout=30,
        )
        if r.status_code >= 300:
            raise HTTPException(502, "Could not store the file. Please try again.")
        return
    full = Path(config.LOCAL_UPLOAD_DIR) / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)


def load(path: str) -> bytes:
    if config.STORAGE_MODE == "supabase":
        r = httpx.get(f"{config.SUPABASE_URL}/storage/v1/object/{config.STORAGE_BUCKET}/{path}",
                      headers=_headers(), timeout=30)
        if r.status_code != 200:
            raise HTTPException(404, "File not found.")
        return r.content
    full = Path(config.LOCAL_UPLOAD_DIR) / path
    if not full.exists():
        raise HTTPException(404, "File not found.")
    return full.read_bytes()


def signed_url(path: str, seconds: int = 120) -> str | None:
    """Short-lived link so a reviewer can view a file. Local mode returns None (use the API route)."""
    if config.STORAGE_MODE != "supabase":
        return None
    r = httpx.post(f"{config.SUPABASE_URL}/storage/v1/object/sign/{config.STORAGE_BUCKET}/{path}",
                   headers=_headers("application/json"), json={"expiresIn": seconds}, timeout=15)
    if r.status_code != 200:
        return None
    return f"{config.SUPABASE_URL}/storage/v1{r.json().get('signedURL', '')}"


def delete(path: str) -> None:
    if config.STORAGE_MODE == "supabase":
        httpx.request("DELETE", f"{config.SUPABASE_URL}/storage/v1/object/{config.STORAGE_BUCKET}",
                      headers=_headers("application/json"), json={"prefixes": [path]}, timeout=15)
        return
    full = Path(config.LOCAL_UPLOAD_DIR) / path
    if full.exists():
        os.remove(full)
