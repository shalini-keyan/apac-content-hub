#!/bin/bash
# Brand Champions — Deploy to apac-brand-champions.quick.shopify.io

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="/tmp/apac-brand-champions"

mkdir -p "$DEPLOY_DIR"

echo "📁 Copying Brand Champions files..."
cp "$SCRIPT_DIR/brand-champions.html" "$DEPLOY_DIR/index.html"

echo ""
echo "🚀 Deploying to apac-brand-champions.quick.shopify.io..."
quick deploy "$DEPLOY_DIR" apac-brand-champions

echo ""
echo "✅ Done! Visit https://apac-brand-champions.quick.shopify.io"
