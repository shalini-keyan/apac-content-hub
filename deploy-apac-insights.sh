#!/bin/bash
# APAC Sales Insights Hub — Deploy
# Run this each week after updating the signals data.
#
# Live site: https://apacinsights.quick.shopify.io
#
# Requires: Shopify `quick` CLI (uses gcloud under the hood for upload).
# If deploy fails with token / Context Aware Access errors, see troubleshooting in the failure message.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/apac-insights-hub"
SITE_NAME="apacinsights"

if [[ ! -d "$DEPLOY_DIR" ]]; then
  echo "Error: deploy directory not found: $DEPLOY_DIR"
  exit 1
fi

if ! command -v quick >/dev/null 2>&1; then
  echo "Error: 'quick' command not found in PATH."
  echo "Install or enable the Shopify Quick CLI (internal static hosting tool), then retry."
  exit 1
fi

echo "🚀 Deploying to ${SITE_NAME}.quick.shopify.io..."
echo "   Source: $DEPLOY_DIR"

if quick deploy --force "$DEPLOY_DIR" "$SITE_NAME"; then
  echo ""
  echo "✅ Done! https://${SITE_NAME}.quick.shopify.io"
else
  code=$?
  echo ""
  echo "✖ Deploy failed (exit $code)."
  echo ""
  echo "Try, in order:"
  echo "  1. gcloud auth login"
  echo "     (fixes \"Context Aware Access\" / token refresh errors on corp machines)"
  echo "  2. quick auth"
  echo "     (refreshes Quick’s Google OAuth if the CLI asks for re-auth)"
  echo "  3. Run this script from a company-managed session (VPN / CRD) if IT requires CAA."
  exit "$code"
fi
