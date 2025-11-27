// LLM Monitor - Options Page
// -*- coding: utf-8 -*-

let currentVersion = { version: '1.0.0', build: 1 };

document.addEventListener('DOMContentLoaded', async () => {
  await loadConfig();
  await loadVersionInfo();
  await checkForUpdates();
  await loadChangelogPreview();
  
  // Event listeners
  document.getElementById('btn-check-update').addEventListener('click', checkForUpdates);
  document.getElementById('btn-bug-report').addEventListener('click', () => openGitHubIssue('bug'));
  document.getElementById('btn-feature-request').addEventListener('click', () => openGitHubIssue('feature'));
  document.getElementById('btn-documentation').addEventListener('click', () => {
    window.open('https://github.com/Gohanado/task-monitoring/wiki', '_blank');
  });
  document.getElementById('btn-github').addEventListener('click', () => {
    window.open('https://github.com/Gohanado/task-monitoring', '_blank');
  });
  document.getElementById('btn-full-changelog').addEventListener('click', () => {
    window.open('https://github.com/Gohanado/task-monitoring/blob/main/monitor/CHANGELOG.md', '_blank');
  });
});

async function loadConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['llmMonitorConfig'], (result) => {
      const config = result.llmMonitorConfig || {};
      document.getElementById('opt-username').textContent = config.username || '-';
      document.getElementById('opt-email').textContent = config.email || '-';
      document.getElementById('opt-server').textContent = config.serverHost 
        ? `${config.serverHost}:${config.serverPort || 8080}` 
        : 'Non configure';
      resolve();
    });
  });
}

async function loadVersionInfo() {
  try {
    const response = await fetch(chrome.runtime.getURL('version.json'));
    currentVersion = await response.json();
    document.getElementById('version-info').textContent = `Version ${currentVersion.version}`;
  } catch (error) {
    console.error('Erreur chargement version:', error);
  }
}

async function checkForUpdates() {
  const statusDiv = document.getElementById('update-status');
  const statusText = statusDiv.querySelector('.status-text');
  const btn = document.getElementById('btn-check-update');
  
  statusDiv.className = 'update-status';
  statusText.textContent = 'Verification...';
  btn.disabled = true;

  try {
    const response = await fetch('https://api.github.com/repos/Gohanado/task-monitoring/releases/latest');
    
    if (!response.ok) {
      statusDiv.classList.add('up-to-date');
      statusText.textContent = 'Vous avez la derniere version';
      btn.disabled = false;
      return;
    }

    const release = await response.json();
    const latestVersion = release.tag_name.replace('v', '');
    
    if (compareVersions(latestVersion, currentVersion.version) > 0) {
      statusDiv.classList.add('update-available');
      statusText.innerHTML = `Nouvelle version disponible: <strong>${latestVersion}</strong>`;
      btn.textContent = 'Telecharger';
      btn.onclick = () => window.open(release.html_url, '_blank');
    } else {
      statusDiv.classList.add('up-to-date');
      statusText.textContent = 'Vous avez la derniere version';
    }
  } catch (error) {
    statusDiv.classList.add('up-to-date');
    statusText.textContent = 'Vous avez la derniere version';
  }
  
  btn.disabled = false;
}

function compareVersions(v1, v2) {
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

async function loadChangelogPreview() {
  const preview = document.getElementById('changelog-preview');
  try {
    const response = await fetch('https://raw.githubusercontent.com/Gohanado/task-monitoring/main/monitor/CHANGELOG.md');
    if (response.ok) {
      const text = await response.text();
      const lines = text.split('\n').slice(0, 20).join('\n');
      preview.innerHTML = formatChangelog(lines);
    } else {
      preview.innerHTML = '<strong>[1.0.0]</strong> - Version initiale';
    }
  } catch (error) {
    preview.innerHTML = '<strong>[1.0.0]</strong> - Version initiale';
  }
}

function formatChangelog(text) {
  return text
    .replace(/^## \[([^\]]+)\]/gm, '<strong>[$1]</strong>')
    .replace(/^### (.+)$/gm, '<br><em>$1</em>')
    .replace(/^- (.+)$/gm, '- $1')
    .replace(/\n/g, '<br>');
}

function openGitHubIssue(type) {
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
- Version: ${currentVersion.version}
- OS: 
- Navigateur: Chrome
`);
    url = `${baseUrl}?labels=bug&title=[Bug]%20&body=${template}`;
  } else {
    const template = encodeURIComponent(`## Description de la fonctionnalite


## Cas d'utilisation


---
Version: ${currentVersion.version}
`);
    url = `${baseUrl}?labels=enhancement&title=[Feature]%20&body=${template}`;
  }
  
  window.open(url, '_blank');
}

