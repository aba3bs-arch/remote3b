#!/bin/bash

# Remote3B Installation Script
# Installs all dependencies and configures the application

set -e

echo "======================================"
echo "  Remote3B - Installation Script"
echo "======================================"
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

python3_version=$(python3 --version | grep -oP '\d+\.\d+')
echo "✓ Python $python3_version found"
echo ""

# Create virtual environment
echo "[2/5] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "[3/5] Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Generate TLS certificates
echo "[4/5] Generating TLS certificates..."
if [ ! -f "certs/cert.pem" ] || [ ! -f "certs/key.pem" ]; then
    python3 generate_certs.py
    echo "✓ Certificates generated"
else
    echo "✓ Certificates already exist"
fi
echo ""

# Create configuration file
echo "[5/5] Creating configuration file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Configuration file created (.env)"
    echo "  Note: Update .env with your settings if needed"
else
    echo "✓ Configuration file already exists"
fi
echo ""

echo "======================================"
echo "  Installation Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Update configuration (optional):"
echo "   vim .env"
echo ""
echo "2. Start the server:"
echo "   source venv/bin/activate"
echo "   python server/main.py"
echo ""
echo "3. In another terminal, start the client:"
echo "   source venv/bin/activate"
echo "   python client/agent.py"
echo ""
echo "4. Open the dashboard:"
echo "   http://localhost:3000"
echo ""
echo "For more information, see README.md"
echo ""
