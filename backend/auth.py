# -*- coding: utf-8 -*-
"""
LLM Monitor - Module d'authentification securise
"""

import os
import json
import secrets
import hashlib
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from jose import JWTError, jwt

# Configuration securite
SECRET_KEY = os.environ.get("LLM_MONITOR_SECRET", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 heures
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Bearer token
security = HTTPBearer(auto_error=False)

# Fichier de base de donnees utilisateurs (simple JSON)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
TOKENS_FILE = DATA_DIR / "tokens.json"
RATE_LIMIT_FILE = DATA_DIR / "rate_limits.json"


# ==================== MODELES ====================

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator('username')
    @classmethod
    def username_valid(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError('Username doit avoir au moins 3 caracteres')
        if not v.isalnum():
            raise ValueError('Username doit etre alphanumerique')
        return v.lower()

    @field_validator('password')
    @classmethod
    def password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Mot de passe doit avoir au moins 8 caracteres')
        if not any(c.isupper() for c in v):
            raise ValueError('Mot de passe doit contenir une majuscule')
        if not any(c.isdigit() for c in v):
            raise ValueError('Mot de passe doit contenir un chiffre')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    exp: Optional[datetime] = None


class User(BaseModel):
    username: str
    email: str
    created_at: str
    is_admin: bool = False
    is_active: bool = True


# ==================== BASE DE DONNEES ====================

def load_users() -> dict:
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_users(users: dict):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def load_tokens() -> dict:
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {"blacklist": []}


def save_tokens(tokens: dict):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)


# ==================== FONCTIONS UTILITAIRES ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=12)
    ).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> Optional[TokenData]:
    try:
        # Verifier si le token est dans la blacklist
        tokens_data = load_tokens()
        if token in tokens_data.get("blacklist", []):
            return None
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != token_type:
            return None
            
        username: str = payload.get("sub")
        if username is None:
            return None
            
        return TokenData(username=username, exp=payload.get("exp"))
    except JWTError:
        return None


def blacklist_token(token: str):
    tokens_data = load_tokens()
    if token not in tokens_data["blacklist"]:
        tokens_data["blacklist"].append(token)
        # Nettoyer les vieux tokens (garder max 1000)
        if len(tokens_data["blacklist"]) > 1000:
            tokens_data["blacklist"] = tokens_data["blacklist"][-500:]
        save_tokens(tokens_data)


# ==================== RATE LIMITING ====================

class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, identifier: str) -> bool:
        now = datetime.utcnow().timestamp()

        if identifier not in self.requests:
            self.requests[identifier] = []

        # Nettoyer les anciennes requetes
        self.requests[identifier] = [
            t for t in self.requests[identifier]
            if now - t < self.window_seconds
        ]

        if len(self.requests[identifier]) >= self.max_requests:
            return False

        self.requests[identifier].append(now)
        return True

    def get_retry_after(self, identifier: str) -> int:
        if identifier not in self.requests or not self.requests[identifier]:
            return 0
        oldest = min(self.requests[identifier])
        return int(self.window_seconds - (datetime.utcnow().timestamp() - oldest))


# Rate limiters
login_limiter = RateLimiter(max_requests=5, window_seconds=300)  # 5 tentatives / 5 min
api_limiter = RateLimiter(max_requests=100, window_seconds=60)   # 100 req / min
register_limiter = RateLimiter(max_requests=3, window_seconds=3600)  # 3 inscriptions / heure


# ==================== AUTHENTIFICATION ====================

def get_user(username: str) -> Optional[dict]:
    users = load_users()
    return users.get(username.lower())


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    if not user.get("is_active", True):
        return None
    return user


def create_user(user_data: UserCreate) -> dict:
    users = load_users()

    username = user_data.username.lower()

    if username in users:
        raise ValueError("Username deja utilise")

    # Verifier email unique
    for u in users.values():
        if u["email"].lower() == user_data.email.lower():
            raise ValueError("Email deja utilise")

    # Creer l'utilisateur
    new_user = {
        "username": username,
        "email": user_data.email.lower(),
        "password_hash": get_password_hash(user_data.password),
        "created_at": datetime.utcnow().isoformat(),
        "is_admin": len(users) == 0,  # Premier utilisateur = admin
        "is_active": True
    }

    users[username] = new_user
    save_users(users)

    return new_user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Dependency pour obtenir l'utilisateur courant"""

    # Rate limiting par IP
    client_ip = request.client.host
    if not api_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requetes. Reessayez plus tard.",
            headers={"Retry-After": str(api_limiter.get_retry_after(client_ip))}
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_data = verify_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expire",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = get_user(token_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouve"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte desactive"
        )

    return User(
        username=user["username"],
        email=user["email"],
        created_at=user["created_at"],
        is_admin=user.get("is_admin", False),
        is_active=user.get("is_active", True)
    )


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[User]:
    """Version optionnelle - retourne None si pas authentifie"""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency pour verifier si l'utilisateur est admin"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces administrateur requis"
        )
    return user

