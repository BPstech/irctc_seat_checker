#!/usr/bin/env bash
# ==============================================================================
# 🚂 IRCTC Green Seat Finder — AWS EC2 (Ubuntu) 1-Click Deployment Script
# Tested on: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS on AWS EC2 (t2.micro / t3.micro)
# ==============================================================================

set -e

echo "=========================================================="
echo "  🚀 Starting IRCTC Seat Finder Deployment on AWS EC2"
echo "=========================================================="

# 1. Require root or sudo privileges
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root or with sudo: sudo bash setup_ec2.sh"
  exit 1
fi

REAL_USER=${SUDO_USER:-$(whoami)}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

echo "[+] Target user: $REAL_USER"
echo "[+] Working directory: $SCRIPT_DIR"

# 2. Configure 2GB Swap Memory (Critical for t2.micro/t3.micro 1GB RAM)
if [ ! -f /swapfile ]; then
    echo "[+] Creating 2GB Swap space (Prevents Chrome Out-Of-Memory crashes)..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    echo "[✓] Swap memory configured successfully."
else
    echo "[✓] Swap file already exists."
fi

# 3. System update & prerequisite packages
echo "[+] Updating system packages..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-pip python3-venv git curl wget unzip \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libcups2 libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 xdg-utils

# 4. Install Google Chrome (Stable)
if ! command -v google-chrome &> /dev/null; then
    echo "[+] Downloading and installing Google Chrome..."
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
    apt-get install -y /tmp/chrome.deb
    rm -f /tmp/chrome.deb
    echo "[✓] Google Chrome installed: $(google-chrome --version)"
else
    echo "[✓] Google Chrome is already installed: $(google-chrome --version)"
fi

# 5. Setup Python Virtual Environment
echo "[+] Setting up Python virtual environment..."
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$REAL_USER" python3 -m venv "$VENV_DIR"
fi

echo "[+] Installing Python dependencies..."
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 6. Setup systemd Service to keep it running 24/7
SERVICE_FILE="/etc/systemd/system/irctc.service"
echo "[+] Configuring systemd background service at $SERVICE_FILE..."

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=IRCTC Green Seat Finder Backend Service
After=network.target

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_DIR/bin/python app.py
Restart=always
RestartSec=5
Environment=PORT=5000
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Reload and start service
systemctl daemon-reload
systemctl enable irctc.service
systemctl restart irctc.service

# 7. Get Public IP
PUBLIC_IP=$(curl -s https://checkip.amazonaws.com || curl -s ifconfig.me || echo "YOUR_EC2_PUBLIC_IP")

echo ""
echo "=========================================================="
echo "  🎉 DEPLOYMENT COMPLETE & SERVICE ONLINE!"
echo "=========================================================="
echo "  • Status: Active and running 24/7 in background"
echo "  • Access URL: http://$PUBLIC_IP:5000"
echo "  • API Health: http://$PUBLIC_IP:5000/health"
echo ""
echo "  Helpful Management Commands:"
echo "    - Check status: sudo systemctl status irctc"
echo "    - View live logs: sudo journalctl -u irctc -f"
echo "    - Restart app: sudo systemctl restart irctc"
echo "    - Stop app: sudo systemctl stop irctc"
echo "=========================================================="
