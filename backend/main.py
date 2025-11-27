# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import asyncio
import json
import re
from datetime import datetime

from models import LLMRequest, RequestStatus
from queue_manager import queue_manager
from services import get_all_services_status, get_ollama_running_models
from ollama_proxy import ollama_proxy
from qdrant_proxy import qdrant_proxy
from auth import (
    UserCreate, UserLogin, Token, User,
    create_user, authenticate_user, get_current_user, get_current_user_optional,
    require_admin, create_access_token, create_refresh_token, verify_token,
    blacklist_token, login_limiter, register_limiter, load_users
)

app = FastAPI(
    title="LLM Monitor",
    version="1.0.0",
    docs_url=None,  # Desactiver Swagger en prod
    redoc_url=None
)

# CORS securise
ALLOWED_ORIGINS = [
    "chrome-extension://*",
    "http://localhost:*",
    "http://127.0.0.1:*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod, limiter aux origines specifiques
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# ==================== MIDDLEWARE SECURITE ====================

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Headers de securite
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ==================== ROUTES AUTHENTIFICATION ====================

@app.post("/api/auth/register", response_model=Token)
async def register(request: Request, user_data: UserCreate):
    """Inscription d'un nouvel utilisateur"""
    client_ip = request.client.host

    # Rate limiting
    if not register_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Reessayez plus tard."
        )

    try:
        user = create_user(user_data)

        # Generer les tokens
        access_token = create_access_token(data={"sub": user["username"]})
        refresh_token = create_refresh_token(data={"sub": user["username"]})

        return Token(access_token=access_token, refresh_token=refresh_token)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login", response_model=Token)
async def login(request: Request, credentials: UserLogin):
    """Connexion utilisateur"""
    client_ip = request.client.host

    # Rate limiting
    if not login_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Reessayez dans 5 minutes."
        )

    user = authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Username ou mot de passe incorrect"
        )

    access_token = create_access_token(data={"sub": user["username"]})
    refresh_token = create_refresh_token(data={"sub": user["username"]})

    return Token(access_token=access_token, refresh_token=refresh_token)


@app.post("/api/auth/refresh", response_model=Token)
async def refresh_token(request: Request):
    """Rafraichir le token d'acces"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")

    token = auth_header.replace("Bearer ", "")
    token_data = verify_token(token, token_type="refresh")

    if not token_data:
        raise HTTPException(status_code=401, detail="Refresh token invalide")

    # Blacklister l'ancien refresh token
    blacklist_token(token)

    # Generer de nouveaux tokens
    access_token = create_access_token(data={"sub": token_data.username})
    new_refresh_token = create_refresh_token(data={"sub": token_data.username})

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Deconnexion - invalide le token"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        blacklist_token(token)
    return {"message": "Deconnecte"}


@app.get("/api/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """Obtenir les infos de l'utilisateur connecte"""
    return current_user


@app.get("/api/auth/check")
async def check_auth():
    """Verifier si l'authentification est requise"""
    users = load_users()
    return {
        "auth_required": len(users) > 0,
        "has_users": len(users) > 0
    }


# API Endpoints
@app.get("/api/queue")
async def get_queue():
    """Retourne les requetes en queue"""
    return [r.model_dump() for r in queue_manager.get_queue()]


@app.get("/api/processing")
async def get_processing():
    """Retourne les requetes en cours"""
    return [r.model_dump() for r in queue_manager.get_processing()]


@app.get("/api/history")
async def get_history(limit: int = 100):
    """Retourne l'historique des requetes"""
    return [r.model_dump() for r in queue_manager.get_history(limit)]


@app.get("/api/stats")
async def get_stats():
    """Retourne les statistiques"""
    return queue_manager.get_stats()


@app.get("/api/services")
async def get_services():
    """Retourne le statut de tous les services"""
    return await get_all_services_status()


@app.get("/api/ollama/models")
async def get_ollama_models():
    """Retourne les modeles Ollama en cours"""
    return await get_ollama_running_models()


# === PROXY OLLAMA ===
@app.post("/ollama/api/generate")
async def proxy_generate(request: Request):
    """Proxy pour Ollama generate"""
    return await ollama_proxy.proxy_generate(request)


@app.post("/ollama/api/chat")
async def proxy_chat(request: Request):
    """Proxy pour Ollama chat"""
    return await ollama_proxy.proxy_chat(request)


@app.api_route("/ollama/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_ollama(request: Request, path: str):
    """Proxy passthrough pour autres endpoints Ollama"""
    # Les routes generate et chat sont gerees par leurs handlers specifiques
    if path == "api/generate" and request.method == "POST":
        return await ollama_proxy.proxy_generate(request)
    if path == "api/chat" and request.method == "POST":
        return await ollama_proxy.proxy_chat(request)
    return await ollama_proxy.proxy_passthrough(request, path)


# === PROXY QDRANT ===
@app.post("/qdrant/collections/{collection}/points/search")
async def proxy_qdrant_search(request: Request, collection: str):
    """Proxy pour Qdrant search - avec queue"""
    return await qdrant_proxy.proxy_search(request, collection)


@app.put("/qdrant/collections/{collection}/points")
async def proxy_qdrant_upsert(request: Request, collection: str):
    """Proxy pour Qdrant upsert - avec queue"""
    return await qdrant_proxy.proxy_upsert(request, collection)


@app.api_route("/qdrant/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_qdrant(request: Request, path: str):
    """Proxy passthrough pour autres endpoints Qdrant"""
    return await qdrant_proxy.proxy_passthrough(request, path)


@app.post("/api/kill/{request_id}")
async def kill_request(request_id: str):
    """Kill une requete"""
    result = await queue_manager.kill_request(request_id)
    if result:
        return {"status": "killed", "request": result.model_dump()}
    raise HTTPException(status_code=404, detail="Request not found")


# Pour les tests: ajouter une requete fictive
@app.post("/api/test/add")
async def add_test_request(service: str = "ollama", model: str = "llama2", prompt: str = "Test"):
    """Ajoute une requete de test"""
    req = LLMRequest(service=service, model=model, prompt=prompt)
    await queue_manager.add_to_queue(req)
    return req.model_dump()


@app.post("/api/test/process/{request_id}")
async def process_test_request(request_id: str):
    """Simule le traitement d'une requete"""
    result = await queue_manager.start_processing(request_id)
    if result:
        return result.model_dump()
    raise HTTPException(status_code=404, detail="Request not found")


@app.post("/api/test/complete/{request_id}")
async def complete_test_request(request_id: str):
    """Simule la completion d'une requete"""
    result = await queue_manager.complete_request(request_id, response="Test response")
    if result:
        return result.model_dump()
    raise HTTPException(status_code=404, detail="Request not found")


# WebSocket pour temps reel
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sub_queue = await queue_manager.subscribe()
    
    try:
        # Envoyer l'etat initial
        initial_data = {
            "queue": [r.model_dump() for r in queue_manager.get_queue()],
            "processing": [r.model_dump() for r in queue_manager.get_processing()],
            "history": [r.model_dump() for r in queue_manager.get_history(50)],
            "stats": queue_manager.get_stats()
        }
        await websocket.send_json(initial_data)
        
        # Ecouter les mises a jour
        while True:
            data = await sub_queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        queue_manager.unsubscribe(sub_queue)
    except Exception as e:
        queue_manager.unsubscribe(sub_queue)


# Servir le frontend
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(BASE_DIR, "frontend", "index.html"))


@app.get("/install.sh")
async def get_install_script():
    """Retourne le script d'installation"""
    script_path = os.path.join(BASE_DIR, "install.sh")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/plain")
    return {"error": "Script not found"}


@app.get("/app.js")
async def get_app_js():
    """Servir app.js depuis static"""
    return FileResponse(os.path.join(BASE_DIR, "static", "app.js"))


@app.get("/style.css")
async def get_style_css():
    """Servir style.css depuis static"""
    return FileResponse(os.path.join(BASE_DIR, "static", "style.css"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

