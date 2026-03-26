#!/bin/bash
# APAC Content Hub — Refresh and Deploy
# Run this whenever your Google Sheet is updated

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="/tmp/apac-content-hub"

echo "📊 Fetching latest data from Google Sheets..."
/Users/shalini.keyan/.local/bin/python3.12 "$SCRIPT_DIR/refresh-assets.py"

echo ""
echo "🔥 Generating Hot This Week..."
/Users/shalini.keyan/.local/bin/python3.12 "$SCRIPT_DIR/generate-hot-this-week.py"

echo ""
echo "📁 Copying files to deploy folder..."
mkdir -p "$DEPLOY_DIR"
cp "$SCRIPT_DIR/content-library.html" "$DEPLOY_DIR/index.html"
cp "$SCRIPT_DIR/assets.json" "$DEPLOY_DIR/assets.json"
cp "$SCRIPT_DIR/hot-this-week.json" "$DEPLOY_DIR/hot-this-week.json"

echo ""
echo "🚀 Deploying to apac-content-hub.quick.shopify.io..."
quick deploy "$DEPLOY_DIR" apac-content-hub

echo ""
echo "✅ Done! Visit https://apac-content-hub.quick.shopify.io"
