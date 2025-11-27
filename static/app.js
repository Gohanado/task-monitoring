// -*- coding: utf-8 -*-
class LLMMonitor {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 3000;
        this.init();
    }

    init() {
        this.connectWebSocket();
        this.loadServices();
        this.loadData(); // Charger les donnees immediatement
        setInterval(() => this.loadServices(), 10000); // Refresh services every 10s
        setInterval(() => this.loadData(), 2000); // Polling toutes les 2s en backup
    }

    async loadData() {
        try {
            const [queue, processing, history, stats] = await Promise.all([
                fetch('/api/queue').then(r => r.json()),
                fetch('/api/processing').then(r => r.json()),
                fetch('/api/history').then(r => r.json()),
                fetch('/api/stats').then(r => r.json())
            ]);
            console.log('Data loaded:', {
                queue: queue.length,
                processing: processing.length,
                history: history.length,
                stats
            });
            this.updateDashboard({ queue, processing, history, stats });
        } catch (error) {
            console.error('Erreur chargement data:', error);
        }
    }

    async loadServices() {
        try {
            const response = await fetch('/api/services');
            const services = await response.json();
            this.renderServices(services);
        } catch (error) {
            console.error('Erreur chargement services:', error);
        }
    }

    renderServices(services) {
        const container = document.getElementById('services-list');
        container.innerHTML = services.map(s => `
            <div class="service-badge">
                <span class="service-dot ${s.status}"></span>
                <span>${s.name}</span>
                <span style="color: var(--text-muted)">:${s.port}</span>
            </div>
        `).join('');
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connecte');
            this.setConnectionStatus(true);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket deconnecte');
            this.setConnectionStatus(false);
            setTimeout(() => this.connectWebSocket(), this.reconnectInterval);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket erreur:', error);
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.updateDashboard(data);
        };
    }

    setConnectionStatus(connected) {
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('connection-text');
        
        if (connected) {
            dot.classList.add('connected');
            text.textContent = 'Connecte';
        } else {
            dot.classList.remove('connected');
            text.textContent = 'Deconnecte';
        }
    }

    updateDashboard(data) {
        // Update stats
        if (data.stats) {
            document.getElementById('stat-queue').textContent = data.stats.queue_count;
            document.getElementById('stat-processing').textContent = data.stats.processing_count;
            document.getElementById('stat-completed').textContent = data.stats.completed_count;
            document.getElementById('stat-failed').textContent = data.stats.failed_count + data.stats.killed_count;
        }

        // Update columns
        this.renderQueue(data.queue || []);
        this.renderProcessing(data.processing || []);
        this.renderHistory(data.history || []);
    }

    renderQueue(requests) {
        const container = document.getElementById('queue-list');
        document.getElementById('queue-count').textContent = requests.length;
        
        if (requests.length === 0) {
            container.innerHTML = '<div class="empty-state">Aucune requete en attente</div>';
            return;
        }
        
        container.innerHTML = requests.map(req => this.renderRequestCard(req, true)).join('');
    }

    renderProcessing(requests) {
        const container = document.getElementById('processing-list');
        document.getElementById('processing-count').textContent = requests.length;
        
        if (requests.length === 0) {
            container.innerHTML = '<div class="empty-state">Aucune requete en traitement</div>';
            return;
        }
        
        container.innerHTML = requests.map(req => this.renderRequestCard(req, true)).join('');
    }

    renderHistory(requests) {
        const container = document.getElementById('history-list');
        document.getElementById('history-count').textContent = requests.length;
        
        if (requests.length === 0) {
            container.innerHTML = '<div class="empty-state">Aucun historique</div>';
            return;
        }
        
        container.innerHTML = requests.map(req => this.renderRequestCard(req, false)).join('');
    }

    renderRequestCard(req, showKill) {
        const time = this.formatTime(req.created_at);
        const killBtn = showKill 
            ? `<button class="btn-kill" onclick="monitor.killRequest('${req.id}')">KILL</button>` 
            : '';
        
        return `
            <div class="request-card">
                <div class="request-header">
                    <div>
                        <div class="request-service">${req.service}</div>
                        <div class="request-model">${req.model}</div>
                    </div>
                    ${killBtn}
                </div>
                <div class="request-prompt" title="${this.escapeHtml(req.prompt)}">${this.escapeHtml(req.prompt)}</div>
                <div class="request-footer">
                    <span class="request-time">${time}</span>
                    <span class="request-status status-${req.status}">${req.status.toUpperCase()}</span>
                </div>
            </div>
        `;
    }

    formatTime(isoString) {
        const date = new Date(isoString);
        return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async killRequest(requestId) {
        try {
            const response = await fetch(`/api/kill/${requestId}`, { method: 'POST' });
            if (!response.ok) {
                console.error('Erreur lors du kill');
            }
        } catch (error) {
            console.error('Erreur:', error);
        }
    }
}

const monitor = new LLMMonitor();

