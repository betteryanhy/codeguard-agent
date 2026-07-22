#!/bin/bash
# =============================================================================
# Trivy Vulnerability Database - Offline Sync Script
# =============================================================================
#
# Usage:
#   1. On a machine WITH internet access, run this script periodically
#      (e.g., every 6 hours via cron) to download the latest vulnerability DB.
#   2. Copy the output directory to your air-gapped GitLab/Agent server.
#   3. The Agent's Trivy scanner will use --skip-db-update + --cache-dir
#      to scan with the pre-synced DB.
#
# Example:
#   ./scripts/update_trivy_db.sh /opt/trivy-db
#   rsync -avz /opt/trivy-db/ user@air-gapped-server:/opt/trivy-db/
#
# Crontab (every 6 hours):
#   0 */6 * * * /path/to/scripts/update_trivy_db.sh /opt/trivy-db
# =============================================================================

set -euo pipefail

CACHE_DIR="${1:-./data/trivy}"
TRIVY_CMD="${TRIVY_CMD:-trivy}"

echo "==> Syncing Trivy vulnerability database to: $CACHE_DIR"
echo "    Command: $TRIVY_CMD"

mkdir -p "$CACHE_DIR"

# Download only the vulnerability database (no scan is performed)
"$TRIVY_CMD" image \
    --download-db-only \
    --cache-dir "$CACHE_DIR"

echo "==> DB sync complete. Cache directory contents:"
ls -lh "$CACHE_DIR"

# Calculate required disk space
DB_SIZE=$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1)
echo "==> Database size: $DB_SIZE"
echo "==> To use on air-gapped server, set in .env:"
echo "    TRIVY_OFFLINE=true"
echo "    TRIVY_CACHE_DIR=$CACHE_DIR"
