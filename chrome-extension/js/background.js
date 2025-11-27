// LLM Monitor - Background Service Worker
// -*- coding: utf-8 -*-

// Configuration
let monitorConfig = null;
let checkInterval = null;

// Creer le menu contextuel au demarrage
chrome.runtime.onInstalled.addListener(() => {
  // Supprimer les anciens menus
  chrome.contextMenus.removeAll(() => {
    // Menu principal
    chrome.contextMenus.create({
      id: 'llm-monitor-options',
      title: 'Options',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-separator1',
      type: 'separator',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-bug',
      title: 'Signaler un bug',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-feature',
      title: 'Demander une amelioration',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-separator2',
      type: 'separator',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-doc',
      title: 'Documentation',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-changelog',
      title: 'Changelog',
      contexts: ['action']
    });

    chrome.contextMenus.create({
      id: 'llm-monitor-github',
      title: 'GitHub',
      contexts: ['action']
    });
  });
});

// Gerer les clics sur le menu contextuel
chrome.contextMenus.onClicked.addListener((info, tab) => {
  const bugTemplate = encodeURIComponent(`## Description du bug

**Comportement attendu:**


**Comportement observe:**


## Etapes pour reproduire
1.
2.
3.

## Environnement
- Version: 1.0.0
- OS:
- Navigateur: Chrome
`);

  const featureTemplate = encodeURIComponent(`## Description de la fonctionnalite


## Cas d'utilisation


## Solution proposee (optionnel)

`);

  switch (info.menuItemId) {
    case 'llm-monitor-options':
      // Ouvrir options dans une fenetre popup
      chrome.windows.create({
        url: chrome.runtime.getURL('options.html'),
        type: 'popup',
        width: 650,
        height: 700,
        focused: true
      });
      break;

    case 'llm-monitor-bug':
      chrome.tabs.create({
        url: `https://github.com/Gohanado/task-monitoring/issues/new?labels=bug&title=[Bug]%20&body=${bugTemplate}`
      });
      break;

    case 'llm-monitor-feature':
      chrome.tabs.create({
        url: `https://github.com/Gohanado/task-monitoring/issues/new?labels=enhancement&title=[Feature]%20&body=${featureTemplate}`
      });
      break;

    case 'llm-monitor-doc':
      chrome.tabs.create({
        url: 'https://github.com/Gohanado/task-monitoring/wiki'
      });
      break;

    case 'llm-monitor-changelog':
      chrome.tabs.create({
        url: 'https://github.com/Gohanado/task-monitoring/blob/main/monitor/CHANGELOG.md'
      });
      break;

    case 'llm-monitor-github':
      chrome.tabs.create({
        url: 'https://github.com/Gohanado/task-monitoring'
      });
      break;
  }
});

// Charger la configuration au demarrage
chrome.storage.local.get(['llmMonitorConfig'], (result) => {
  monitorConfig = result.llmMonitorConfig || null;
  if (monitorConfig) {
    startMonitoring();
  }
});

// Ecouter les changements de configuration
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local' && changes.llmMonitorConfig) {
    monitorConfig = changes.llmMonitorConfig.newValue;
    if (monitorConfig) {
      startMonitoring();
    } else {
      stopMonitoring();
    }
  }
});

// Demarrer le monitoring
function startMonitoring() {
  if (checkInterval) {
    clearInterval(checkInterval);
  }
  
  // Verification toutes les 30 secondes
  checkInterval = setInterval(checkServerStatus, 30000);
  checkServerStatus();
}

// Arreter le monitoring
function stopMonitoring() {
  if (checkInterval) {
    clearInterval(checkInterval);
    checkInterval = null;
  }
  updateBadge(null);
}

// Verifier le statut du serveur
async function checkServerStatus() {
  if (!monitorConfig || !monitorConfig.host) {
    updateBadge(null);
    return;
  }
  
  try {
    const response = await fetch(`${monitorConfig.host}/api/stats`, {
      signal: AbortSignal.timeout(5000)
    });
    
    if (!response.ok) throw new Error('Server error');
    
    const stats = await response.json();
    
    // Mettre a jour le badge avec le nombre en queue + processing
    const activeCount = (stats.queue_count || 0) + (stats.processing_count || 0);
    updateBadge(activeCount);
    
    // Notification si beaucoup de requetes en queue
    if (stats.queue_count > 50) {
      showNotification(
        'File d\'attente importante',
        `${stats.queue_count} requetes en attente sur ${monitorConfig.host}`
      );
    }
    
  } catch (error) {
    console.error('Check status error:', error);
    updateBadge('!');
  }
}

// Mettre a jour le badge de l'icone
function updateBadge(value) {
  if (value === null) {
    chrome.action.setBadgeText({ text: '' });
  } else if (value === '!') {
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#e74c3c' });
  } else if (value === 0) {
    chrome.action.setBadgeText({ text: '' });
  } else {
    chrome.action.setBadgeText({ text: String(value) });
    chrome.action.setBadgeBackgroundColor({ color: '#00d4ff' });
  }
}

// Afficher une notification
function showNotification(title, message) {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title: title,
    message: message
  });
}

// API pour le popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getStatus') {
    checkServerStatus().then(() => {
      sendResponse({ success: true });
    });
    return true;
  }
  
  if (request.action === 'testConnection') {
    testConnection(request.host).then(result => {
      sendResponse(result);
    });
    return true;
  }
});

// Tester la connexion a un serveur
async function testConnection(host) {
  try {
    const response = await fetch(`${host}/api/stats`, {
      signal: AbortSignal.timeout(5000)
    });
    
    if (!response.ok) {
      return { success: false, error: `HTTP ${response.status}` };
    }
    
    const data = await response.json();
    return { success: true, data };
    
  } catch (error) {
    return { success: false, error: error.message };
  }
}

console.log('LLM Monitor background service started');

