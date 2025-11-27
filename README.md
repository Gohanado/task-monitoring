# LLM Monitor

Systeme de monitoring temps reel pour Ollama et Qdrant.

## Fonctionnalites

- Monitoring temps reel des requetes LLM
- Extension Chrome pour visualisation
- Proxy transparent pour Ollama et Qdrant
- Systeme de queue pour les requetes
- Authentification securisee (SHA-256 + bcrypt)
- Dashboard avec statistiques en temps reel

## Installation

### Prerequis

- Ubuntu/Debian, CentOS/RHEL ou macOS
- Python 3.8+
- MySQL 5.7+ ou MariaDB
- Chrome/Chromium

### Installation rapide

```bash
git clone https://github.com/Gohanado/task-monitoring.git
cd task-monitoring/monitor
chmod +x install.sh
./install.sh
```

### Extension Chrome

1. Ouvrir `chrome://extensions/`
2. Activer "Mode developpeur"
3. Cliquer "Charger l'extension non empaquetee"
4. Selectionner le dossier `monitor/chrome-extension`

## Utilisation

1. Lancer le service monitoring : `./start.sh`
2. Ouvrir l'extension Chrome
3. S'inscrire/Se connecter
4. Configurer l'IP de votre serveur

## Architecture

```
monitor/
  backend/          # Service monitoring local (port 8080)
  central/          # Service auth central (port 8081)
  chrome-extension/ # Extension Chrome
  install.sh        # Script d'installation
```

## Securite

- Mots de passe hashes cote client (SHA-256) puis serveur (bcrypt)
- JWT tokens avec expiration
- Rate limiting sur login/register
- Pas de stockage de donnees sensibles dans l'extension

## Licence

Propriétaire - Voir LICENSE
Copyright (c) 2024 Gohanado

## Support

- [Signaler un bug](https://github.com/Gohanado/task-monitoring/issues/new?labels=bug)
- [Demander une fonctionnalite](https://github.com/Gohanado/task-monitoring/issues/new?labels=enhancement)

