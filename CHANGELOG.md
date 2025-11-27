# Changelog

Toutes les modifications notables de ce projet seront documentees dans ce fichier.

Le format est base sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [1.0.0] - 2024-11-27

### Ajoute
- Systeme d'authentification securise avec hash SHA-256 cote client + bcrypt serveur
- Extension Chrome pour le monitoring
- Service central d'authentification (port 8081)
- Service de monitoring local (port 8080)
- Proxy Ollama et Qdrant avec tracking des requetes
- Dashboard temps reel avec statistiques
- Systeme de queue pour les requetes
- Rate limiting pour la securite
- Option "Se souvenir de moi" pour les sessions longues
- Menu Options avec bug report, feature request et documentation
- Systeme de mise a jour automatique depuis GitHub

### Securite
- Mots de passe jamais transmis en clair (hash SHA-256 cote client)
- Double hashage (SHA-256 + bcrypt) pour le stockage
- JWT tokens avec expiration configurable
- Rate limiting sur login et register
- Validation des entrees utilisateur

