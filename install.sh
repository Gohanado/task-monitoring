#!/bin/bash
# -*- coding: utf-8 -*-
# LLM Monitor - Script d'installation
# Usage: ./install.sh [PORT]

set -e

PORT=${1:-8080}

echo "========================================"
echo "   LLM Monitor - Installation"
echo "========================================"
echo ""
echo "Port: $PORT"
echo ""

# Detecter l'OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
fi

echo "[1/4] Installation des dependances..."
case $OS in
    ubuntu|debian)
        sudo apt update -qq
        sudo apt install -y python3 python3-pip python3-venv -qq
        ;;
    centos|rhel|fedora)
        sudo yum install -y python3 python3-pip -q 2>/dev/null || sudo dnf install -y python3 python3-pip -q
        ;;
    darwin)
        brew install python3 2>/dev/null || true
        ;;
    *)
        echo "OS non supporte. Installez Python 3 manuellement."
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[2/4] Creation de l'environnement virtuel..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "[3/4] Installation des packages Python..."
pip install --upgrade pip -q
pip install fastapi uvicorn httpx websockets bcrypt pydantic -q

echo "[4/4] Configuration..."
cat > start_monitor.sh << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
EOF
chmod +x start_monitor.sh

echo ""
echo "========================================"
echo "   Installation terminee!"
echo "========================================"
echo ""
echo "Pour demarrer:"
echo "  ./start_monitor.sh"
echo ""
echo "IMPORTANT: Ouvrez le port $PORT dans votre pare-feu!"
echo ""
