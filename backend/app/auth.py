"""Who is calling? Returns a CurrentUser with id, email, role, email_verified.

AUTH_MODE=dev       -> header  X-Demo-User: ravi@demo.test   (no Supabase needed, for local testing)
AUTH_MODE=supabase  -> header  Authorization: Bearer <access token from supabase-js>
                       The token is checked by asking Supabase Auth who it belongs to,
                       so it works with both old (HS256) and new (asymmetric) Supabase JWT keys.

Roles are decided on the server (never trust the frontend):
reviewer if email is in REVIEWER_EMAILS, service_verifier if in VERIFIER_EMAILS, otherwise user.
"""
import time
import uuid
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException

from . import config


@dataclass
class CurrentUser:
    id: str
    email: str
    role: str            # user / reviewer / service_verifier
    email_verified: bool


def _role_for(email: str) -> str:
    e = email.lower()
    if e in config.REVIEWER_EMAILS:
        return "reviewer"
    if e in config.VERIFIER_EMAILS:
        return "service_verifier"
    return "user"


_cache: dict[str, tuple[float, CurrentUser]] = {}


def _from_supabase(token: str) -> CurrentUser:
    hit = _cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise HTTPException(500, "Server auth is not configured (SUPABASE_URL / SUPABASE_ANON_KEY).")
    try:
        r = httpx.get(
            f"{config.SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": config.SUPABASE_ANON_KEY},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Could not reach the authentication service. Try again.")
    if r.status_code != 200:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    data = r.json()
    email = data.get("email") or ""
    user = CurrentUser(
        id=data["id"],
        email=email,
        role=_role_for(email),
        email_verified=bool(data.get("email_confirmed_at") or data.get("confirmed_at")),
    )
    _cache[token] = (time.time() + 60, user)
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
) -> CurrentUser:
    if config.AUTH_MODE == "dev":
        if not x_demo_user:
            raise HTTPException(401, "Dev mode: send header X-Demo-User: <email>")
        email = x_demo_user.strip().lower()
        return CurrentUser(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"drift-demo:{email}")),
            email=email, role=_role_for(email), email_verified=True,
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    return _from_supabase(authorization.split(" ", 1)[1].strip())


def require_role(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "You don't have access to this page.")
        return user
    return checker
