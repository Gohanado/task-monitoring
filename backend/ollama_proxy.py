# -*- coding: utf-8 -*-
"""
Proxy pour intercepter les requetes Ollama et les mettre en queue
Traitement sequentiel - 1 requete a la fois
"""
import asyncio
import httpx
import json
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse

from models import LLMRequest, RequestStatus
from queue_manager import queue_manager

OLLAMA_URL = "http://127.0.0.1:11434"
MAX_CONCURRENT = 1  # Nombre max de requetes simultanees


class OllamaProxy:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=300.0)
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.pending_requests: Dict[str, asyncio.Event] = {}

    async def proxy_generate(self, request: Request) -> StreamingResponse:
        """Proxy pour /api/generate avec queue"""
        body = await request.json()

        # Creer une requete trackee
        llm_req = LLMRequest(
            service="ollama",
            model=body.get("model", "unknown"),
            prompt=body.get("prompt", "")[:500],
            metadata={
                "full_prompt_length": len(body.get("prompt", "")),
                "stream": body.get("stream", True),
                "options": body.get("options", {})
            }
        )

        # Ajouter a la queue (status = queued)
        await queue_manager.add_to_queue(llm_req)

        # Creer un event pour cette requete
        ready_event = asyncio.Event()
        self.pending_requests[llm_req.id] = ready_event

        async def stream_response():
            try:
                # Attendre notre tour (semaphore)
                async with self.semaphore:
                    # Maintenant on peut traiter - passer en processing
                    await queue_manager.start_processing(llm_req.id)

                    async with self.client.stream(
                        "POST",
                        f"{OLLAMA_URL}/api/generate",
                        json=body,
                        timeout=300.0
                    ) as response:
                        full_response = ""
                        async for chunk in response.aiter_bytes():
                            yield chunk
                            try:
                                data = json.loads(chunk.decode())
                                if "response" in data:
                                    full_response += data["response"]
                            except:
                                pass

                        await queue_manager.complete_request(llm_req.id, response=full_response[:500])
            except Exception as e:
                await queue_manager.complete_request(llm_req.id, error=str(e))
                raise
            finally:
                self.pending_requests.pop(llm_req.id, None)

        return StreamingResponse(stream_response(), media_type="application/x-ndjson")
    
    async def proxy_chat(self, request: Request) -> StreamingResponse:
        """Proxy pour /api/chat avec queue"""
        body = await request.json()
        messages = body.get("messages", [])
        last_msg = messages[-1].get("content", "") if messages else ""

        llm_req = LLMRequest(
            service="ollama",
            model=body.get("model", "unknown"),
            prompt=last_msg[:500],
            metadata={
                "message_count": len(messages),
                "stream": body.get("stream", True)
            }
        )

        await queue_manager.add_to_queue(llm_req)
        self.pending_requests[llm_req.id] = asyncio.Event()

        async def stream_response():
            try:
                async with self.semaphore:
                    await queue_manager.start_processing(llm_req.id)

                    async with self.client.stream(
                        "POST",
                        f"{OLLAMA_URL}/api/chat",
                        json=body,
                        timeout=300.0
                    ) as response:
                        full_response = ""
                        async for chunk in response.aiter_bytes():
                            yield chunk
                            try:
                                data = json.loads(chunk.decode())
                                if "message" in data and "content" in data["message"]:
                                    full_response += data["message"]["content"]
                            except:
                                pass
                        await queue_manager.complete_request(llm_req.id, response=full_response[:500])
            except Exception as e:
                await queue_manager.complete_request(llm_req.id, error=str(e))
                raise
            finally:
                self.pending_requests.pop(llm_req.id, None)

        return StreamingResponse(stream_response(), media_type="application/x-ndjson")
    
    async def proxy_passthrough(self, request: Request, path: str):
        """Proxy passthrough pour autres endpoints"""
        method = request.method
        body = await request.body() if method in ["POST", "PUT", "PATCH"] else None
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=f"{OLLAMA_URL}/{path}",
                content=body,
                headers={"Content-Type": "application/json"}
            )
            return JSONResponse(content=response.json(), status_code=response.status_code)


ollama_proxy = OllamaProxy()

