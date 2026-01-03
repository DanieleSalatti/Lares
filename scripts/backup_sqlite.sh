#!/bin/bash
# SQLite backup script for Lares
# Backs up lares.db to a local folder with rotation

set -e

BACKUP_DIR="/home/daniele/backups/lares"
DB_PATH="/home/daniele/workspace/lares/data/lares.db"
MAX_BACKUPS=7  # Keep a week of daily backups

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create timestamped backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/lares_$TIMESTAMP.db"

# Use SQLite's backup command for safe copy
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress the backup
gzip "$BACKUP_FILE"

echo "Backup created: ${BACKUP_FILE}.gz"

# Remove old backups (keep only MAX_BACKUPS most recent)
ls -t "$BACKUP_DIR"/lares_*.db.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm --

echo "Backup complete. Kept last $MAX_BACKUPS backups."
ls -la "$BACKUP_DIR"
