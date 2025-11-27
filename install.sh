#!/usr/bin/env bash
set -e

SOURCE_URL="https://raw.githubusercontent.com/V1337Q/ghpeek/main"
INSTALL_DIR="$HOME/.local/share/ghpeek"
BIN_DIR="$HOME/.local/bin"

echo "📥 Installing ghpeek..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Download main script
curl -s "$SOURCE_URL/ghpeek.py" -o "$INSTALL_DIR/ghpeek.py"
curl -s "$SOURCE_URL/requirements.txt" -o "$INSTALL_DIR/requirements.txt"

# Download launcher
curl -s "$SOURCE_URL/ghpeek" -o "$BIN_DIR/ghpeek"
chmod +x "$BIN_DIR/ghpeek"

echo "✨ Installation complete!"
echo
echo "Ensure ~/.local/bin is in PATH:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo
echo "Try:"
echo "  ghpeek folke"
