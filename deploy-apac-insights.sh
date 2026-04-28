#!/bin/bash
# APAC Sales Insights Hub — Deploy
# Run this each week after updating the signals data.
#
# Workflow:
#   1. Run the data refresh (update apac-insights-hub/index.html with new CSVs)
#   2. Run this script to deploy to quick.shopify.io

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/apac-insights-hub"

echo "🚀 Deploying to apacinsights.quick.shopify.io..."
quick deploy "$DEPLOY_DIR" apacinsights

echo ""
echo "✅ Done! Visit https://apacinsights.quick.shopify.io"
