#!/bin/bash
set -euo pipefail

# If running as root, fix volume permissions, seed existing db/uploads, and drop to ctfd user
if [ "$(id -u)" = "0" ]; then
    mkdir -p /var/uploads /var/log/CTFd
    chown -R 1001:1001 /var/uploads /var/log/CTFd 2>/dev/null || true
    chmod -R 775 /var/uploads /var/log/CTFd 2>/dev/null || true

    # Seed the persistent volume with our existing ctfd.db if it does not yet exist on disk
    if [ -f "/opt/CTFd/CTFd/ctfd.db" ] && [ ! -f "/var/uploads/ctfd.db" ]; then
        echo "[+] Seeding /var/uploads/ctfd.db from existing database..."
        cp /opt/CTFd/CTFd/ctfd.db /var/uploads/ctfd.db
        chown 1001:1001 /var/uploads/ctfd.db 2>/dev/null || true
        chmod 664 /var/uploads/ctfd.db 2>/dev/null || true
    fi

    # Seed challenge uploads into /var/uploads if missing
    if [ -d "/opt/CTFd/CTFd/uploads" ]; then
        echo "[+] Seeding existing challenge uploads to /var/uploads..."
        cp -rn /opt/CTFd/CTFd/uploads/* /var/uploads/ 2>/dev/null || true
        chown -R 1001:1001 /var/uploads 2>/dev/null || true
    fi

    # Re-execute as ctfd user (1001)
    exec su -s /bin/bash ctfd "$0" "$@"
fi

WORKERS=${WORKERS:-1}
WORKER_CLASS=${WORKER_CLASS:-gthread}
THREADS=${THREADS:-8}
ACCESS_LOG=${ACCESS_LOG:--}
ERROR_LOG=${ERROR_LOG:--}
WORKER_TEMP_DIR=${WORKER_TEMP_DIR:-/dev/shm}
SECRET_KEY=${SECRET_KEY:-}
SKIP_DB_PING=${SKIP_DB_PING:-false}

# Check that a .ctfd_secret_key file or SECRET_KEY envvar is set
if [ ! -f .ctfd_secret_key ] && [ -z "$SECRET_KEY" ]; then
    if [ $WORKERS -gt 1 ]; then
        echo "[ ERROR ] You are configured to use more than 1 worker."
        echo "[ ERROR ] To do this, you must define the SECRET_KEY environment variable or create a .ctfd_secret_key file."
        echo "[ ERROR ] Exiting..."
        exit 1
    fi
fi

# Skip db ping if SKIP_DB_PING is set to a value other than false or empty string
if [[ "$SKIP_DB_PING" == "false" ]]; then
  # Ensures that the database is available
  python ping.py
fi

# Initialize database
flask db upgrade

# Start CTFd
echo "Starting CTFd"
exec gunicorn 'CTFd:create_app()' \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers $WORKERS \
    --worker-class "$WORKER_CLASS" \
    --threads $THREADS \
    --worker-tmp-dir "$WORKER_TEMP_DIR" \
    --access-logfile "$ACCESS_LOG" \
    --error-logfile "$ERROR_LOG"
