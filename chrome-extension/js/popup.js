// LLM Monitor - Popup Script
// -*- coding: utf-8 -*-

// URL du service central d'authentification
const CENTRAL_API = 'http://83.228.205.172:8081';

// Hash SHA-256 cote client - le mot de passe ne transite jamais en clair
async function hashPassword(password, username) {
  const salt = 'LLM_MONITOR_2024_';
  const data = salt + username.toLowerCase() + ':' + password;
  const encoder = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

class LLMMonitor {
  constructor() {
    this.config = null;
    this.refreshInterval = null;
    this.selectedOS = null;
    this.selectedPort = 8080;
    this.init();
  }

  async init() {
    // Charger la config sauvegardee
    this.config = await this.loadConfig();

    // Event listeners - Auth centrale
    document.querySelectorAll('.auth-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchAuthTab(tab.dataset.tab));
    });
    document.getElementById('login-form').addEventListener('submit', (e) => this.handleLogin(e));
    document.getElementById('register-form').addEventListener('submit', (e) => this.handleRegister(e));

    // Event listeners - Server config
    document.getElementById('btn-logout').addEventListener('click', () => this.logout());
    document.getElementById('btn-new-install').addEventListener('click', () => this.showView('install-step1'));
    document.getElementById('server-form').addEventListener('submit', (e) => this.handleServerConnect(e));

    // Event listeners - Dashboard
    document.getElementById('btn-disconnect').addEventListener('click', () => this.disconnectServer());
    document.getElementById('btn-open-dashboard').addEventListener('click', () => this.openDashboard());

    // Event listeners - Install Step 1 (OS)
    document.getElementById('btn-back-welcome2').addEventListener('click', () => this.showView('server-view'));
    document.querySelectorAll('.os-btn').forEach(btn => {
      btn.addEventListener('click', () => this.selectOS(btn.dataset.os));
    });

    // Event listeners - Install Step 2 (Commands)
    document.getElementById('btn-back-step1').addEventListener('click', () => this.showView('install-step1'));
    document.getElementById('btn-copy-commands').addEventListener('click', () => this.copyCommands());
    document.getElementById('btn-next-step3').addEventListener('click', () => this.goToStep3());
    document.getElementById('install-port').addEventListener('change', (e) => this.updatePort(e.target.value));

    // Event listeners - Install Step 3 (Test)
    document.getElementById('btn-back-step2').addEventListener('click', () => this.showView('install-step2'));
    document.getElementById('btn-test-connection').addEventListener('click', () => this.testConnection());
    document.getElementById('btn-finish-install').addEventListener('click', () => this.finishInstall());
    document.getElementById('btn-retry-install').addEventListener('click', () => this.showView('install-step1'));

    // Event listeners - Options
    document.getElementById('btn-options').addEventListener('click', () => this.showOptions());
    document.getElementById('btn-back-options').addEventListener('click', () => this.showView('dashboard-view'));
    document.getElementById('btn-check-update').addEventListener('click', () => this.checkForUpdates());
    document.getElementById('btn-bug-report').addEventListener('click', () => this.openGitHubIssue('bug'));
    document.getElementById('btn-feature-request').addEventListener('click', () => this.openGitHubIssue('feature'));
    document.getElementById('btn-documentation').addEventListener('click', () => this.openDocumentation());
    document.getElementById('btn-full-changelog').addEventListener('click', () => this.openFullChangelog());

    // Verifier si deja connecte au service central
    if (this.config && this.config.centralToken) {
      const isValid = await this.validateCentralToken();
      if (isValid) {
        // Connecte au central, verifier si serveur local configure
        if (this.config.serverHost) {
          this.showView('dashboard-view');
          this.startRefresh();
        } else {
          this.showView('server-view');
          this.updateUserInfo();
        }
      } else {
        this.showView('auth-view');
      }
    } else {
      this.showView('auth-view');
    }
  }

  async loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['llmMonitorConfig'], (result) => {
        resolve(result.llmMonitorConfig || null);
      });
    });
  }

  async saveConfig(config) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ llmMonitorConfig: config }, resolve);
    });
  }

  updateUserInfo() {
    if (this.config && this.config.username) {
      document.getElementById('user-info').textContent = `Connecte: ${this.config.username}`;
    }
  }

  switchAuthTab(tab) {
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

    if (tab === 'login') {
      document.getElementById('login-form').classList.remove('hidden');
      document.getElementById('register-form').classList.add('hidden');
    } else {
      document.getElementById('login-form').classList.add('hidden');
      document.getElementById('register-form').classList.remove('hidden');
    }
  }

  // === AUTH CENTRALE ===
  async handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const rememberMe = document.getElementById('remember-me').checked;
    const errorDiv = document.getElementById('auth-error');
    const btn = e.target.querySelector('button[type="submit"]');
    errorDiv.classList.add('hidden');

    btn.textContent = 'Connexion...';
    btn.disabled = true;

    try {
      // Hash du mot de passe cote client - ne transite jamais en clair
      const passwordHash = await hashPassword(password, username);

      const response = await fetch(`${CENTRAL_API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password_hash: passwordHash, remember_me: rememberMe })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Echec de connexion');
      }

      this.config = {
        centralToken: data.access_token,
        centralRefresh: data.refresh_token,
        username: data.user.username,
        email: data.user.email,
        rememberMe: rememberMe
      };
      await this.saveConfig(this.config);

      this.showView('server-view');
      this.updateUserInfo();

    } catch (error) {
      console.error('Login error:', error);
      errorDiv.textContent = error.message || 'Erreur de connexion au serveur';
      errorDiv.classList.remove('hidden');
    } finally {
      btn.textContent = 'Se connecter';
      btn.disabled = false;
    }
  }

  async handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('reg-username').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const password2 = document.getElementById('reg-password2').value;
    const errorDiv = document.getElementById('auth-error');
    const btn = e.target.querySelector('button[type="submit"]');
    errorDiv.classList.add('hidden');

    // Validation cote client
    if (password !== password2) {
      errorDiv.textContent = 'Les mots de passe ne correspondent pas';
      errorDiv.classList.remove('hidden');
      return;
    }

    if (password.length < 8) {
      errorDiv.textContent = 'Mot de passe: minimum 8 caracteres';
      errorDiv.classList.remove('hidden');
      return;
    }

    if (!/[A-Z]/.test(password) || !/[0-9]/.test(password)) {
      errorDiv.textContent = 'Mot de passe: 1 majuscule et 1 chiffre requis';
      errorDiv.classList.remove('hidden');
      return;
    }

    btn.textContent = 'Inscription...';
    btn.disabled = true;

    try {
      // Hash du mot de passe cote client - ne transite jamais en clair
      const passwordHash = await hashPassword(password, username);

      const response = await fetch(`${CENTRAL_API}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password_hash: passwordHash })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Echec inscription');
      }

      this.config = {
        centralToken: data.access_token,
        centralRefresh: data.refresh_token,
        username: data.user.username,
        email: data.user.email
      };
      await this.saveConfig(this.config);

      this.showView('server-view');
      this.updateUserInfo();

    } catch (error) {
      console.error('Register error:', error);
      errorDiv.textContent = error.message || 'Erreur de connexion au serveur';
      errorDiv.classList.remove('hidden');
    } finally {
      btn.textContent = "S'inscrire";
      btn.disabled = false;
    }
  }

  async validateCentralToken() {
    if (!this.config || !this.config.centralToken) return false;
    try {
      const response = await fetch(`${CENTRAL_API}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${this.config.centralToken}` },
        signal: AbortSignal.timeout(5000)
      });
      if (response.ok) return true;
      if (this.config.centralRefresh) {
        return await this.refreshCentralToken();
      }
      return false;
    } catch {
      return false;
    }
  }

  async refreshCentralToken() {
    try {
      const response = await fetch(`${CENTRAL_API}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${this.config.centralRefresh}` }
      });
      if (!response.ok) return false;
      const tokens = await response.json();
      this.config.centralToken = tokens.access_token;
      this.config.centralRefresh = tokens.refresh_token;
      await this.saveConfig(this.config);
      return true;
    } catch {
      return false;
    }
  }

  async logout() {
    this.stopRefresh();
    this.config = null;
    chrome.storage.local.remove(['llmMonitorConfig']);
    this.showView('auth-view');
  }

  // === SERVEUR LOCAL ===
  async handleServerConnect(e) {
    e.preventDefault();
    const host = document.getElementById('server-host').value.trim();
    const port = document.getElementById('server-port').value || '8080';
    const errorDiv = document.getElementById('server-error');
    errorDiv.classList.add('hidden');

    if (!host) {
      errorDiv.textContent = 'Adresse requise';
      errorDiv.classList.remove('hidden');
      return;
    }

    let serverUrl = host;
    if (!serverUrl.startsWith('http://') && !serverUrl.startsWith('https://')) {
      serverUrl = 'http://' + serverUrl;
    }
    serverUrl = serverUrl + ':' + port;

    try {
      const response = await fetch(`${serverUrl}/api/stats`, {
        signal: AbortSignal.timeout(5000)
      });
      if (!response.ok) throw new Error('Serveur inaccessible');

      this.config.serverHost = serverUrl;
      await this.saveConfig(this.config);

      this.showView('dashboard-view');
      this.startRefresh();

    } catch (error) {
      errorDiv.textContent = `Erreur: ${error.message}`;
      errorDiv.classList.remove('hidden');
    }
  }

  async disconnectServer() {
    this.stopRefresh();
    if (this.config) {
      delete this.config.serverHost;
      await this.saveConfig(this.config);
    }
    this.showView('server-view');
    this.updateUserInfo();
  }

  showView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    document.getElementById(viewId).classList.remove('hidden');

    if (viewId === 'dashboard-view' && this.config && this.config.serverHost) {
      const userInfo = this.config.username ? ` (${this.config.username})` : '';
      document.getElementById('server-info').textContent = this.config.serverHost + userInfo;
    }
  }

  // === INSTALLATION ===
  selectOS(os) {
    this.selectedOS = os;
    document.querySelectorAll('.os-btn').forEach(btn => btn.classList.remove('selected'));
    document.querySelector(`[data-os="${os}"]`).classList.add('selected');
    this.generateCommands(os, this.selectedPort);
    this.showView('install-step2');
  }

  updatePort(port) {
    this.selectedPort = parseInt(port) || 8080;
    document.getElementById('port-display').textContent = this.selectedPort;
    if (this.selectedOS) {
      this.generateCommands(this.selectedOS, this.selectedPort);
    }
  }

  generateCommands(os, port = 8080) {
    const commands = {
      ubuntu: `# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git

# Cloner le projet
git clone https://github.com/Gohanado/task-monitoring.git
cd task-monitoring/monitor

# Installer
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn httpx websockets

# Demarrer (port ${port})
uvicorn backend.main:app --host 0.0.0.0 --port ${port}`,

      centos: `# CentOS / RHEL
sudo yum install -y python3 python3-pip git

# Cloner le projet
git clone https://github.com/Gohanado/task-monitoring.git
cd task-monitoring/monitor

# Installer
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn httpx websockets

# Ouvrir le pare-feu
sudo firewall-cmd --add-port=${port}/tcp --permanent && sudo firewall-cmd --reload

# Demarrer (port ${port})
uvicorn backend.main:app --host 0.0.0.0 --port ${port}`,

      macos: `# macOS
brew install python3 git

# Cloner le projet
git clone https://github.com/Gohanado/task-monitoring.git
cd task-monitoring/monitor

# Installer
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn httpx websockets

# Demarrer (port ${port})
uvicorn backend.main:app --host 0.0.0.0 --port ${port}`
    };

    document.getElementById('install-commands').textContent = commands[os] || commands.ubuntu;
  }

  copyCommands() {
    const commands = document.getElementById('install-commands').textContent;
    navigator.clipboard.writeText(commands).then(() => {
      const btn = document.getElementById('btn-copy-commands');
      btn.textContent = 'Copie!';
      setTimeout(() => { btn.textContent = 'Copier'; }, 2000);
    });
  }

  goToStep3() {
    document.getElementById('test-port').value = this.selectedPort;
    this.showView('install-step3');
  }

  async testConnection() {
    const ip = document.getElementById('test-ip').value.trim();
    const port = document.getElementById('test-port').value || this.selectedPort;
    if (!ip) return;

    let host = ip;
    if (!host.startsWith('http://') && !host.startsWith('https://')) {
      host = 'http://' + host;
    }
    host = host + ':' + port;

    document.getElementById('test-success').classList.add('hidden');
    document.getElementById('test-error').classList.add('hidden');

    const btn = document.getElementById('btn-test-connection');
    btn.textContent = 'Test...';
    btn.disabled = true;

    try {
      const response = await fetch(`${host}/api/stats`, {
        signal: AbortSignal.timeout(5000)
      });

      if (!response.ok) throw new Error('Erreur serveur');

      this.testedHost = host;
      document.getElementById('test-success').classList.remove('hidden');

    } catch (error) {
      document.getElementById('test-error').classList.remove('hidden');
    }

    btn.textContent = 'Tester';
    btn.disabled = false;
  }

  async finishInstall() {
    if (this.testedHost) {
      this.config.serverHost = this.testedHost;
      await this.saveConfig(this.config);
      this.showView('dashboard-view');
      this.startRefresh();
    }
  }

  // === DASHBOARD ===
  startRefresh() {
    this.refresh();
    this.refreshInterval = setInterval(() => this.refresh(), 2000);
  }

  stopRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  async refresh() {
    if (!this.config || !this.config.serverHost) return;

    try {
      const [services, stats, queue, processing] = await Promise.all([
        this.fetchData('/api/services'),
        this.fetchData('/api/stats'),
        this.fetchData('/api/queue'),
        this.fetchData('/api/processing')
      ]);

      this.renderServices(services);
      this.renderStats(stats);
      this.renderQueue(queue);
      this.renderProcessing(processing);

    } catch (error) {
      console.error('Refresh error:', error);
    }
  }

  async fetchData(endpoint) {
    const response = await fetch(`${this.config.serverHost}${endpoint}`);
    return response.json();
  }

  renderServices(services) {
    const container = document.getElementById('services-list');
    container.innerHTML = services.map(s => `
      <div class="service-card">
        <span class="service-status ${s.status}"></span>
        <span class="service-name">${s.name}</span>
        <span class="service-port">:${s.port}</span>
      </div>
    `).join('');
  }

  renderStats(stats) {
    document.getElementById('stat-queue').textContent = stats.queue_count || 0;
    document.getElementById('stat-processing').textContent = stats.processing_count || 0;
    document.getElementById('stat-completed').textContent = stats.completed_count || 0;
    document.getElementById('stat-failed').textContent = (stats.failed_count || 0) + (stats.killed_count || 0);
  }

  renderQueue(queue) {
    const container = document.getElementById('queue-list');
    document.getElementById('queue-count').textContent = queue.length;

    if (queue.length === 0) {
      container.innerHTML = '<div class="empty-list">Aucune requete en attente</div>';
      return;
    }

    container.innerHTML = queue.slice(0, 10).map(r => `
      <div class="request-item">
        <span class="request-service ${r.service}">${r.service}</span>
        <span class="request-prompt">${this.escapeHtml(r.prompt)}</span>
        <button class="request-kill" data-id="${r.id}">KILL</button>
      </div>
    `).join('');

    // Ajouter les event listeners pour kill
    container.querySelectorAll('.request-kill').forEach(btn => {
      btn.addEventListener('click', () => this.killRequest(btn.dataset.id));
    });
  }

  renderProcessing(processing) {
    const container = document.getElementById('processing-list');
    document.getElementById('processing-count').textContent = processing.length;

    if (processing.length === 0) {
      container.innerHTML = '<div class="empty-list">Aucune requete en cours</div>';
      return;
    }

    container.innerHTML = processing.map(r => `
      <div class="request-item">
        <span class="request-service ${r.service}">${r.service}</span>
        <span class="request-prompt">${this.escapeHtml(r.prompt)}</span>
        <button class="request-kill" data-id="${r.id}">KILL</button>
      </div>
    `).join('');

    container.querySelectorAll('.request-kill').forEach(btn => {
      btn.addEventListener('click', () => this.killRequest(btn.dataset.id));
    });
  }

  async killRequest(requestId) {
    try {
      await fetch(`${this.config.serverHost}/api/kill/${requestId}`, { method: 'POST' });
      this.refresh();
    } catch (error) {
      console.error('Kill error:', error);
    }
  }

  openDashboard() {
    if (this.config && this.config.serverHost) {
      chrome.tabs.create({ url: this.config.serverHost });
    }
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // === OPTIONS ===
  async showOptions() {
    this.showView('options-view');

    // Afficher les infos utilisateur
    document.getElementById('opt-username').textContent = this.config?.username || '-';
    document.getElementById('opt-email').textContent = this.config?.email || '-';
    document.getElementById('opt-server').textContent = this.config?.serverHost
      ? `${this.config.serverHost}:${this.config.serverPort || 8080}`
      : 'Non configure';

    // Charger la version et le changelog
    await this.loadVersionInfo();
    await this.checkForUpdates();
  }

  async loadVersionInfo() {
    try {
      const response = await fetch(chrome.runtime.getURL('version.json'));
      this.currentVersion = await response.json();
      document.getElementById('version-info').textContent = `Version ${this.currentVersion.version}`;
    } catch (error) {
      console.error('Erreur chargement version:', error);
      this.currentVersion = { version: '1.0.0', build: 1 };
    }
  }

  async checkForUpdates() {
    const statusDiv = document.getElementById('update-status');
    const statusText = statusDiv.querySelector('.status-text');

    statusDiv.className = 'update-status';
    statusText.textContent = 'Verification...';

    try {
      const response = await fetch('https://api.github.com/repos/Gohanado/task-monitoring/releases/latest');

      if (!response.ok) {
        // Pas de release encore
        statusDiv.classList.add('up-to-date');
        statusText.textContent = 'Vous avez la derniere version';
        this.loadChangelogPreview();
        return;
      }

      const release = await response.json();
      const latestVersion = release.tag_name.replace('v', '');

      if (this.compareVersions(latestVersion, this.currentVersion?.version || '1.0.0') > 0) {
        statusDiv.classList.add('update-available');
        statusText.innerHTML = `Nouvelle version disponible: <strong>${latestVersion}</strong>`;

        // Ajouter bouton de mise a jour
        const btn = document.getElementById('btn-check-update');
        btn.textContent = 'Telecharger la mise a jour';
        btn.onclick = () => window.open(release.html_url, '_blank');
      } else {
        statusDiv.classList.add('up-to-date');
        statusText.textContent = 'Vous avez la derniere version';
      }

      this.loadChangelogPreview();
    } catch (error) {
      console.error('Erreur verification MAJ:', error);
      statusDiv.classList.add('up-to-date');
      statusText.textContent = 'Vous avez la derniere version';
      this.loadChangelogPreview();
    }
  }

  compareVersions(v1, v2) {
    const parts1 = v1.split('.').map(Number);
    const parts2 = v2.split('.').map(Number);

    for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
      const p1 = parts1[i] || 0;
      const p2 = parts2[i] || 0;
      if (p1 > p2) return 1;
      if (p1 < p2) return -1;
    }
    return 0;
  }

  async loadChangelogPreview() {
    const preview = document.getElementById('changelog-preview');
    try {
      const response = await fetch('https://raw.githubusercontent.com/Gohanado/task-monitoring/main/monitor/CHANGELOG.md');
      if (response.ok) {
        const text = await response.text();
        // Extraire les 10 premieres lignes significatives
        const lines = text.split('\n').slice(0, 15).join('\n');
        preview.innerHTML = this.formatChangelog(lines);
      } else {
        preview.innerHTML = '<strong>[1.0.0]</strong> - Version initiale';
      }
    } catch (error) {
      preview.innerHTML = '<strong>[1.0.0]</strong> - Version initiale';
    }
  }

  formatChangelog(text) {
    return text
      .replace(/^## \[([^\]]+)\]/gm, '<strong>[$1]</strong>')
      .replace(/^### (.+)$/gm, '<br><em>$1</em>')
      .replace(/^- (.+)$/gm, '- $1')
      .replace(/\n/g, '<br>');
  }

  openGitHubIssue(type) {
    const baseUrl = 'https://github.com/Gohanado/task-monitoring/issues/new';
    let url;

    if (type === 'bug') {
      const template = encodeURIComponent(`## Description du bug

**Comportement attendu:**


**Comportement observe:**


## Etapes pour reproduire
1.
2.
3.

## Environnement
- Version: ${this.currentVersion?.version || '1.0.0'}
- OS:
- Navigateur: Chrome

## Captures d'ecran (si applicable)
`);
      url = `${baseUrl}?labels=bug&title=[Bug]%20&body=${template}`;
    } else {
      const template = encodeURIComponent(`## Description de la fonctionnalite


## Cas d'utilisation


## Solution proposee (optionnel)


## Alternatives considerees (optionnel)


---
Version: ${this.currentVersion?.version || '1.0.0'}
`);
      url = `${baseUrl}?labels=enhancement&title=[Feature]%20&body=${template}`;
    }

    window.open(url, '_blank');
  }

  openDocumentation() {
    window.open('https://github.com/Gohanado/task-monitoring/wiki', '_blank');
  }

  openFullChangelog() {
    window.open('https://github.com/Gohanado/task-monitoring/blob/main/monitor/CHANGELOG.md', '_blank');
  }
}

// Initialiser
document.addEventListener('DOMContentLoaded', () => {
  new LLMMonitor();
});
