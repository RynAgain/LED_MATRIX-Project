#!/bin/bash
# Wrapper script for safely installing LED Matrix systemd service files.
# Only copies files from the project's services/ directory to /etc/systemd/system/
# and applies path/user substitutions. Called via sudoers (no wildcard arguments).
#
# Usage: sudo /path/to/install-service-files.sh <project_root> <actual_user> <actual_home>

set -euo pipefail

PROJECT_ROOT="${1:?Usage: $0 <project_root> <actual_user> <actual_home>}"
ACTUAL_USER="${2:?}"
ACTUAL_HOME="${3:?}"

SERVICES_DIR="$PROJECT_ROOT/services"
ALLOWED_FILES="led-matrix.service led-matrix-updater.service led-matrix-updater.timer"

if [ ! -d "$SERVICES_DIR" ]; then
    echo "ERROR: services dir not found: $SERVICES_DIR" >&2
    exit 1
fi

for SVC_FILE in $ALLOWED_FILES; do
    SRC="$SERVICES_DIR/$SVC_FILE"
    DST="/etc/systemd/system/$SVC_FILE"
    if [ -f "$SRC" ]; then
        cp "$SRC" "$DST"
        sed -i "s|/home/ryn/LED_MATRIX-Project|$PROJECT_ROOT|g" "$DST"
        sed -i "s|User=ryn|User=$ACTUAL_USER|g" "$DST"
        sed -i "s|Group=ryn|Group=$ACTUAL_USER|g" "$DST"
        sed -i "s|HOME=/home/ryn|HOME=$ACTUAL_HOME|g" "$DST"
        chmod 644 "$DST"
        echo "Installed $SVC_FILE"
    fi
done

systemctl daemon-reload
