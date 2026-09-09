#!/bin/sh
set -e

# Wait for database using Python
if [ "$DATABASE_URL" ]; then
    echo "Waiting for database..."
    python -c "
import os, time, socket
from urllib.parse import urlparse
url = urlparse(os.environ.get('DATABASE_URL', ''))
host = url.hostname
port = url.port or 5432
if host:
    while True:
        try:
            socket.create_connection((host, port), timeout=1)
            break
        except OSError:
            time.sleep(0.5)
"
    echo "Database is ready."
fi

# Apply migrations
echo "Applying migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start server
exec "$@"
