"""JWT bearer authentication for the admin API."""

import hmac
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.models import utcnow

bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def check_credentials(username: str, password: str) -> bool:
    s = get_settings()
    return hmac.compare_digest(username, s.admin_username) & hmac.compare_digest(password, s.admin_password)


def create_token(subject: str) -> str:
    s = get_settings()
    payload = {"sub": subject, "exp": utcnow() + timedelta(minutes=s.jwt_ttl_minutes), "scope": "admin"}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("scope") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient scope")
    return payload["sub"]
