#!/bin/bash
# cc-cost installer — one command, no thinking required.
# Usage: curl -fsSL https://raw.githubusercontent.com/Hedyzhang-Ading/cc-cost/main/install.sh | bash

set -e

INSTALL_DIR="$HOME/.claude/skills/cc-cost"
REPO_URL="https://github.com/Hedyzhang-Ading/cc-cost.git"

echo "📦 Installing cc-cost..."

# 1. Handle existing install
if [ -d "$INSTALL_DIR" ]; then
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "   Updating existing install..."
        cd "$INSTALL_DIR"
        git pull --ff-only 2>/dev/null && echo "   ✅ Updated." && exit 0
        cd "$HOME"
    fi
    echo "   Removing old install..."
    rm -rf "$INSTALL_DIR"
fi

# 2. Clone
echo "   Cloning $REPO_URL ..."
mkdir -p "$(dirname "$INSTALL_DIR")"
for i in 1 2 3; do
    if git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null; then
        break
    fi
    echo "   Retry $i/3..."
    rm -rf "$INSTALL_DIR"
    sleep 2
done

# 3. Verify
if [ ! -f "$INSTALL_DIR/run.py" ]; then
    echo "❌ Install failed. Please try again or check your network."
    exit 1
fi

echo ""
echo "✅ cc-cost installed!"
echo ""
echo "   Try it now:"
echo "     /cc-cost"
echo "     /cc-cost report"
echo "     /cc-cost compare"
echo ""
echo "   Or in Claude: just ask 'how much did I spend today?'"
