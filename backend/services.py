# -*- coding: utf-8 -*-
"""
Configuration des services LLM a monitorer
"""
from dataclasses import dataclass
from typing import List, Optional
import httpx


@dataclass
class ServiceConfig:
    name: str
    host: str
    port: int
    api_base: str
    health_endpoint: Optional[str] = None
    ps_endpoint: Optional[str] = None  # Pour voir les requetes en cours
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}{self.api_base}"


# Services detectes sur ce serveur
SERVICES: List[ServiceConfig] = [
    ServiceConfig(
        name="ollama",
        host="127.0.0.1",
        port=11434,
        api_base="/api",
        health_endpoint="/api/tags",
        ps_endpoint="/api/ps"
    ),
    ServiceConfig(
        name="qdrant",
        host="127.0.0.1",
        port=6333,
        api_base="",
        health_endpoint="/healthz"
    ),
]


async def check_service_health(service: ServiceConfig) -> dict:
    """Verifie la sante d'un service"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if service.health_endpoint:
                url = f"http://{service.host}:{service.port}{service.health_endpoint}"
                response = await client.get(url)
                return {
                    "name": service.name,
                    "status": "online" if response.status_code == 200 else "error",
                    "port": service.port,
                    "response_code": response.status_code
                }
    except Exception as e:
        return {
            "name": service.name,
            "status": "offline",
            "port": service.port,
            "error": str(e)
        }
    return {"name": service.name, "status": "unknown", "port": service.port}


async def get_ollama_running_models() -> dict:
    """Recupere les modeles en cours d'execution sur Ollama"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://127.0.0.1:11434/api/ps")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        return {"error": str(e), "models": []}
    return {"models": []}


async def get_all_services_status() -> List[dict]:
    """Recupere le statut de tous les services"""
    results = []
    for service in SERVICES:
        status = await check_service_health(service)
        results.append(status)
    return results

