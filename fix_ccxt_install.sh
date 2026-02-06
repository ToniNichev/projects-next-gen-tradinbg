#!/bin/bash
# Fix corrupted ccxt installation

echo "Fixing corrupted ccxt installation..."

# Activate the virtual environment where ccxt is installed
# Adjust this path if your venv is in a different location
VENV_PATH="/Users/toninichev/Applications/trading.toninichev.com/venv"

if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
    echo "✓ Activated virtual environment: $VENV_PATH"
else
    echo "⚠ Virtual environment not found at $VENV_PATH"
    echo "Using current Python environment..."
fi

# Uninstall corrupted ccxt
echo "Uninstalling corrupted ccxt..."
pip uninstall -y ccxt

# Clear pip cache to remove corrupted files
echo "Clearing pip cache..."
pip cache purge

# Upgrade pip, setuptools, and wheel to ensure clean installs
echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

# Reinstall ccxt with fresh download
echo "Reinstalling ccxt..."
pip install --no-cache-dir ccxt>=4.0.0

# Verify installation
echo "Verifying ccxt installation..."
python3 -c "import ccxt; print(f'✓ ccxt version: {ccxt.__version__}')"

echo ""
echo "✓ ccxt installation fixed! You can now run: pip install -r requirements.txt"
