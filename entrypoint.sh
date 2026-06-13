#!/bin/bash
set -e

echo "Initializing Cobalt..."
python -c "from app.db.session import init_db; init_db()"

exec "$@"
