#!/bin/bash
# Database and Configuration Backup Script

BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Creating backup..."
tar -czf "$BACKUP_FILE" \
    --exclude='venv' \
    --exclude='backups' \
    --exclude='logs/*.log' \
    .env \
    data/ \
    *.py \
    requirements.txt

echo "✓ Backup created: $BACKUP_FILE"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/backup_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true
echo "✓ Old backups cleaned up"
