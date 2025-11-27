# -*- coding: utf-8 -*-
"""
Proxy pour intercepter les requetes Qdrant et les mettre en queue
Traitement sequentiel pour les operations lourdes (search, upsert)
"""
import asyncio
import httpx
import json
from typing import Dict
from fastapi import Request
from fastapi.responses import JSONResponse

from models import LLMRequest
from queue_manager import queue_manager

QDRANT_URL = "http://127.0.0.1:6333"
MAX_CONCURRENT = 1  # Nombre max de requetes simultanees


class QdrantProxy:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.pending_requests: Dict[str, asyncio.Event] = {}

    async def proxy_search(self, request: Request, collection: str) -> JSONResponse:
        """Proxy pour /collections/{collection}/points/search avec queue"""
        body = await request.json()

        # Creer une requete trackee
        llm_req = LLMRequest(
            service="qdrant",
            model=collection,
            prompt=f"search (limit={body.get('limit', 10)})",
            metadata={
                "operation": "search",
                "limit": body.get("limit", 10),
                "with_payload": body.get("with_payload", True)
            }
        )

        await queue_manager.add_to_queue(llm_req)
        self.pending_requests[llm_req.id] = asyncio.Event()

        try:
            async with self.semaphore:
                await queue_manager.start_processing(llm_req.id)

                response = await self.client.post(
                    f"{QDRANT_URL}/collections/{collection}/points/search",
                    json=body,
                    timeout=60.0
                )
                result = response.json()
                
                points_count = len(result.get("result", []))
                await queue_manager.complete_request(
                    llm_req.id, 
                    response=f"{points_count} points found"
                )
                return JSONResponse(content=result, status_code=response.status_code)
        except Exception as e:
            await queue_manager.complete_request(llm_req.id, error=str(e))
            raise
        finally:
            self.pending_requests.pop(llm_req.id, None)

    async def proxy_upsert(self, request: Request, collection: str) -> JSONResponse:
        """Proxy pour /collections/{collection}/points avec queue"""
        body = await request.json()
        points = body.get("points", [])

        llm_req = LLMRequest(
            service="qdrant",
            model=collection,
            prompt=f"upsert ({len(points)} points)",
            metadata={
                "operation": "upsert",
                "points_count": len(points)
            }
        )

        await queue_manager.add_to_queue(llm_req)
        self.pending_requests[llm_req.id] = asyncio.Event()

        try:
            async with self.semaphore:
                await queue_manager.start_processing(llm_req.id)

                response = await self.client.put(
                    f"{QDRANT_URL}/collections/{collection}/points",
                    json=body,
                    timeout=60.0
                )
                result = response.json()
                
                await queue_manager.complete_request(
                    llm_req.id, 
                    response=f"upserted {len(points)} points"
                )
                return JSONResponse(content=result, status_code=response.status_code)
        except Exception as e:
            await queue_manager.complete_request(llm_req.id, error=str(e))
            raise
        finally:
            self.pending_requests.pop(llm_req.id, None)

    async def proxy_passthrough(self, request: Request, path: str):
        """Proxy passthrough pour autres endpoints (collections list, etc.)"""
        method = request.method
        body = await request.body() if method in ["POST", "PUT", "PATCH"] else None
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=f"{QDRANT_URL}/{path}",
                content=body,
                headers={"Content-Type": "application/json"} if body else {}
            )
            try:
                return JSONResponse(content=response.json(), status_code=response.status_code)
            except:
                return JSONResponse(content={"raw": response.text}, status_code=response.status_code)


qdrant_proxy = QdrantProxy()

