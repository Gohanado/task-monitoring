# -*- coding: utf-8 -*-
"""
LLM Monitor - Service Central d'Authentification
Ce service gere les inscriptions et connexions des utilisateurs
"""

import os
import bcrypt
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from jose import JWTError, jwt
from dotenv import load_dotenv

# Charger .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'database': os.getenv('DB_NAME', 'llm_monitor'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'pool_name': 'llm_pool',
    'pool_size': 5
}

JWT_SECRET = os.getenv('JWT_SECRET')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 1440))
REFRESH_TOKEN_EXPIRE = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', 30))

# Pool de connexions MySQL
db_pool = mysql.connector.pooling.MySQLConnectionPool(**DB_CONFIG)

# FastAPI
app = FastAPI(title="LLM Monitor Central", version="1.0.0")
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting simple
rate_limits = {}

def check_rate_limit(ip: str, action: str, max_requests: int, window: int) -> bool:
    key = f"{ip}:{action}"
    now = datetime.utcnow().timestamp()
    if key not in rate_limits:
        rate_limits[key] = []
    rate_limits[key] = [t for t in rate_limits[key] if now - t < window]
    if len(rate_limits[key]) >= max_requests:
        return False
    rate_limits[key].append(now)
    return True


@contextmanager
def get_db():
    conn = db_pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ==================== MODELES ====================

class UserRegister(BaseModel):
    username: str
    email: str
    password_hash: str  # Hash SHA-256 du mot de passe (hashe cote client)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError('Username: minimum 3 caracteres')
        if not v.isalnum():
            raise ValueError('Username: alphanumerique uniquement')
        return v.lower()

    @field_validator('password_hash')
    @classmethod
    def validate_password_hash(cls, v: str) -> str:
        # Le hash SHA-256 fait exactement 64 caracteres hexadecimaux
        if len(v) != 64 or not all(c in '0123456789abcdef' for c in v):
            raise ValueError('Hash de mot de passe invalide')
        return v


class UserLogin(BaseModel):
    username: str
    password_hash: str  # Hash SHA-256 du mot de passe (hashe cote client)
    remember_me: bool = False  # Session longue duree


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


# ==================== FONCTIONS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(data: dict, token_type: str, expires_minutes: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {**data, "exp": expire, "type": token_type}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ==================== ROUTES ====================

@app.get("/")
async def root():
    return {"service": "LLM Monitor Central", "version": "1.0.0"}


@app.post("/api/auth/register", response_model=Token)
async def register(request: Request, data: UserRegister):
    client_ip = request.client.host

    if not check_rate_limit(client_ip, "register", 3, 3600):
        raise HTTPException(429, "Trop de tentatives. Reessayez dans 1 heure.")

    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)

        # Verifier username unique
        cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
        if cursor.fetchone():
            raise HTTPException(400, "Ce nom d'utilisateur existe deja")

        # Verifier email unique
        cursor.execute("SELECT id FROM users WHERE email = %s", (data.email.lower(),))
        if cursor.fetchone():
            raise HTTPException(400, "Cet email est deja utilise")

        # Creer l'utilisateur - double hash: SHA-256 (client) + bcrypt (serveur)
        final_hash = hash_password(data.password_hash)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (data.username, data.email.lower(), final_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid

        cursor.close()

    # Generer les tokens
    token_data = {"sub": data.username, "user_id": user_id}
    access_token = create_token(token_data, "access", ACCESS_TOKEN_EXPIRE)
    refresh_token = create_token(token_data, "refresh", REFRESH_TOKEN_EXPIRE * 24 * 60)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"username": data.username, "email": data.email.lower()}
    )


@app.post("/api/auth/login", response_model=Token)
async def login(request: Request, data: UserLogin):
    client_ip = request.client.host

    if not check_rate_limit(client_ip, "login", 5, 300):
        raise HTTPException(429, "Trop de tentatives. Reessayez dans 5 minutes.")

    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, username, email, password_hash, is_active FROM users WHERE username = %s",
            (data.username.lower(),)
        )
        user = cursor.fetchone()
        cursor.close()

    # Verification: compare SHA-256 (client) hashe avec bcrypt (serveur)
    if not user or not verify_password(data.password_hash, user['password_hash']):
        raise HTTPException(401, "Identifiants incorrects")

    if not user['is_active']:
        raise HTTPException(403, "Compte desactive")

    # Mise a jour last_login
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user['id'],))
        conn.commit()
        cursor.close()

    token_data = {"sub": user['username'], "user_id": user['id']}
    access_token = create_token(token_data, "access", ACCESS_TOKEN_EXPIRE)
    refresh_token = create_token(token_data, "refresh", REFRESH_TOKEN_EXPIRE * 24 * 60)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"username": user['username'], "email": user['email']}
    )


@app.get("/api/auth/me")
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Token requis")

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "Token invalide")

    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT username, email, is_premium, created_at FROM users WHERE username = %s",
            (payload['sub'],)
        )
        user = cursor.fetchone()
        cursor.close()

    if not user:
        raise HTTPException(404, "Utilisateur non trouve")

    user['created_at'] = user['created_at'].isoformat() if user['created_at'] else None
    return user


@app.post("/api/auth/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Refresh token requis")

    payload = verify_token(credentials.credentials)
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(401, "Refresh token invalide")

    token_data = {"sub": payload['sub'], "user_id": payload['user_id']}
    access_token = create_token(token_data, "access", ACCESS_TOKEN_EXPIRE)
    new_refresh = create_token(token_data, "refresh", REFRESH_TOKEN_EXPIRE * 24 * 60)

    return {"access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer"}


@app.get("/api/auth/check")
async def check_service():
    return {"status": "ok", "service": "central"}

