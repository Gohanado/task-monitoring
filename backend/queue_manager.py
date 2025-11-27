# -*- coding: utf-8 -*-
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
from models import LLMRequest, RequestStatus


class QueueManager:
    """Gestionnaire de queue pour les requetes LLM"""
    
    def __init__(self):
        self.queue: deque[LLMRequest] = deque()
        self.processing: Dict[str, LLMRequest] = {}
        self.history: List[LLMRequest] = []
        self.max_history = 1000
        self._lock = asyncio.Lock()
        self._subscribers: List[asyncio.Queue] = []
    
    async def add_to_queue(self, request: LLMRequest) -> LLMRequest:
        """Ajoute une requete a la queue"""
        async with self._lock:
            request.status = RequestStatus.QUEUED
            request.created_at = datetime.utcnow()
            self.queue.append(request)
            await self._notify_subscribers()
        return request
    
    async def start_processing(self, request_id: str) -> Optional[LLMRequest]:
        """Deplace une requete de la queue vers processing"""
        async with self._lock:
            for i, req in enumerate(self.queue):
                if req.id == request_id:
                    req = self.queue[i]
                    del self.queue[i]
                    req.status = RequestStatus.PROCESSING
                    req.started_at = datetime.utcnow()
                    self.processing[request_id] = req
                    await self._notify_subscribers()
                    return req
        return None
    
    async def complete_request(self, request_id: str, response: str = None, error: str = None) -> Optional[LLMRequest]:
        """Termine une requete et la deplace vers l'historique"""
        async with self._lock:
            if request_id in self.processing:
                req = self.processing.pop(request_id)
                req.completed_at = datetime.utcnow()
                req.response = response
                req.error = error
                req.status = RequestStatus.COMPLETED if not error else RequestStatus.FAILED
                self.history.insert(0, req)
                if len(self.history) > self.max_history:
                    self.history.pop()
                await self._notify_subscribers()
                return req
        return None
    
    async def kill_request(self, request_id: str) -> Optional[LLMRequest]:
        """Kill une requete (queue ou processing)"""
        async with self._lock:
            # Chercher dans la queue
            for i, req in enumerate(self.queue):
                if req.id == request_id:
                    req = self.queue[i]
                    del self.queue[i]
                    req.status = RequestStatus.KILLED
                    req.completed_at = datetime.utcnow()
                    self.history.insert(0, req)
                    await self._notify_subscribers()
                    return req
            
            # Chercher dans processing
            if request_id in self.processing:
                req = self.processing.pop(request_id)
                req.status = RequestStatus.KILLED
                req.completed_at = datetime.utcnow()
                self.history.insert(0, req)
                await self._notify_subscribers()
                return req
        return None
    
    def get_queue(self) -> List[LLMRequest]:
        return list(self.queue)
    
    def get_processing(self) -> List[LLMRequest]:
        return list(self.processing.values())
    
    def get_history(self, limit: int = 100) -> List[LLMRequest]:
        return self.history[:limit]
    
    def get_stats(self) -> dict:
        return {
            "queue_count": len(self.queue),
            "processing_count": len(self.processing),
            "completed_count": len([h for h in self.history if h.status == RequestStatus.COMPLETED]),
            "failed_count": len([h for h in self.history if h.status == RequestStatus.FAILED]),
            "killed_count": len([h for h in self.history if h.status == RequestStatus.KILLED])
        }
    
    async def subscribe(self) -> asyncio.Queue:
        """S'abonner aux mises a jour"""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue):
        """Se desabonner"""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
    
    async def _notify_subscribers(self):
        """Notifie tous les abonnes d'un changement"""
        data = {
            "queue": [r.model_dump() for r in self.get_queue()],
            "processing": [r.model_dump() for r in self.get_processing()],
            "history": [r.model_dump() for r in self.get_history(50)],
            "stats": self.get_stats()
        }
        for sub in self._subscribers:
            try:
                await sub.put(data)
            except:
                pass


# Instance globale
queue_manager = QueueManager()

