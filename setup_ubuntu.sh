#!/usr/bin/env bash
set -e

echo "=================================================================="
echo "   [IRCTC] Green Seat Finder -- Ubuntu Server Auto-Installer"
echo "=================================================================="
echo ""

# 1. Update apt and install system prerequisites
echo "[1/4] Installing system packages (python3, pip, curl, wget)..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv wget curl ca-certificates gnupg

# 2. Install Google Chrome (required for headless Selenium scraping)
echo "[2/4] Installing Google Chrome..."
if ! command -v google-chrome &> /dev/null && ! command -v google-chrome-stable &> /dev/null; then
    wget -q -O /tmp/google-chrome-stable.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt install -y /tmp/google-chrome-stable.deb
    rm -f /tmp/google-chrome-stable.deb
    echo "      Google Chrome installed successfully."
else
    echo "      Google Chrome is already installed."
fi

# 3. Create virtual environment & install requirements
echo "[3/4] Setting up Python virtual environment and dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Make scripts executable
echo "[4/4] Setting permissions..."
chmod +x host_tunnel.py 2>/dev/null || true
if [ -f "run_ubuntu.sh" ]; then
    chmod +x run_ubuntu.sh
fi

echo ""
echo "=================================================================="
echo "  [SUCCESS] SETUP COMPLETE!"
echo "=================================================================="
echo ""
echo "  To start your live backend:"
echo "    ./run_ubuntu.sh"
echo ""
echo "  Or start with python directly:"
echo "    source venv/bin/activate && python3 host_tunnel.py"
echo "=================================================================="
